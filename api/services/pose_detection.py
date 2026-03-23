"""
Pose-based throw-segment detection and throw-type classification for dg-form.

The single public function ``detect_throw_segment`` implements two algorithms
in a single MediaPipe Pose pass:

1. **Auto-trim** — locate the highest-velocity wrist-motion window and pad it
   by 500 ms each side.
2. **Throw-type** — classify "backhand" | "forehand" | "unknown" from the net
   cross-body wrist travel within the detected segment.

Call site (upload.py)::

    result = await asyncio.to_thread(detect_throw_segment, temp_path)

Both algorithms share a single ``mp.solutions.pose.Pose`` context; the object
is *not* cached at module level because MediaPipe Pose is not thread-safe.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TypedDict

import cv2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------

# Landmark visibility below this value is treated as "landmark not detected".
_MIN_VISIBILITY: float = 0.5

# Rolling-mean window (in sampled frames) for smoothing the velocity signal.
_SMOOTH_WINDOW: int = 7

# Minimum number of high-confidence frames required; below this → fallback.
_FALLBACK_THRESHOLD: int = 10

# Signal energy below this value → no discernible throw motion → fallback.
_MIN_PEAK_ENERGY: float = 0.005

# Window is expanded from the peak frame until energy drops below this
# fraction of the peak value.
_PEAK_THRESHOLD_RATIO: float = 0.20

# Padding added to each side of the detected motion window (milliseconds).
_PAD_MS: int = 500

# Maximum number of frames submitted to MediaPipe; excess frames are skipped
# via stride so processing time scales to O(_MAX_POSE_FRAMES) not O(duration).
_MAX_POSE_FRAMES: int = 600

# Normalised-coordinate wrist displacement thresholds for throw classification.
_CROSS_BODY_THRESHOLD: float = 0.25   # |delta| must exceed this to classify
_EXPECTED_MAX_DELTA: float = 0.60     # denominator for confidence ratio
_MIN_THROW_TYPE_CONFIDENCE: float = 0.70  # below this → return "unknown"
_ONE_WRIST_PENALTY: float = 0.80      # confidence penalty when one wrist absent


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

class _LMData(TypedDict):
    x: float
    y: float
    v: float  # visibility score in [0, 1]


class _FrameData(TypedDict):
    frame_idx: int
    timestamp_ms: float
    left_wrist: _LMData | None
    right_wrist: _LMData | None
    left_shoulder: _LMData | None
    right_shoulder: _LMData | None


# ---------------------------------------------------------------------------
# Private helpers — landmark extraction
# ---------------------------------------------------------------------------

def _extract_lm(landmarks, idx: int) -> _LMData | None:
    """Return a landmark dict if visibility ≥ threshold, else None."""
    lm = landmarks.landmark[idx]
    if lm.visibility < _MIN_VISIBILITY:
        return None
    return {"x": lm.x, "y": lm.y, "v": lm.visibility}


def _get_wrist(fd: _FrameData, side: str) -> _LMData | None:
    """Return the wrist for *side* ('left' or 'right') from a frame record."""
    return fd["left_wrist"] if side == "left" else fd["right_wrist"]


# ---------------------------------------------------------------------------
# Private helpers — the pose pass
# ---------------------------------------------------------------------------

def _run_pose_pass(
    video_path: Path,
    pose,
) -> tuple[list[_FrameData], float, int, int]:
    """
    Process *video_path* through *pose* and return per-sampled-frame pose data.

    A stride is computed so that at most ``_MAX_POSE_FRAMES`` frames are
    submitted to MediaPipe.  Timestamps are derived from the *original* frame
    index, so they remain accurate regardless of stride.

    Because callers use ``static_image_mode=True``, each frame is processed
    independently and any stride is safe (no tracking state is broken).

    Returns:
        frame_data  – pose result for every sampled frame (may include None
                      landmarks when pose was not detected)
        fps         – source video frame rate
        frame_count – total original frame count
        duration_ms – total source duration in ms
    """
    import mediapipe as mp  # imported lazily; guarded at the call site
    PL = mp.solutions.pose.PoseLandmark

    cap = cv2.VideoCapture(str(video_path))
    try:
        fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_ms: int = int((frame_count / fps) * 1000)
        stride: int = max(1, frame_count // _MAX_POSE_FRAMES)

        logger.info(
            "Pose pass: %d frames @ %.1f fps, stride=%d (~%d frames to process)",
            frame_count, fps, stride, frame_count // stride,
        )

        frame_data: list[_FrameData] = []
        raw_idx: int = 0

        while True:
            if raw_idx % stride == 0:
                # Hard cap: stop sampling once we have enough frames.
                # Guards against CAP_PROP_FRAME_COUNT underreporting.
                if len(frame_data) >= _MAX_POSE_FRAMES:
                    break

                ret, bgr = cap.read()
                if not ret:
                    break
            else:
                # Advance the demuxer without decompressing the frame.
                if not cap.grab():
                    break
                raw_idx += 1
                continue

            timestamp_ms: float = (raw_idx / fps) * 1000.0

            # Resize to at most 640 px wide for speed.
            h, w = bgr.shape[:2]
            if w > 640:
                bgr = cv2.resize(bgr, (640, int(h * 640.0 / w)))

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            lms = result.pose_landmarks

            if lms is not None:
                fd: _FrameData = {
                    "frame_idx":      raw_idx,
                    "timestamp_ms":   timestamp_ms,
                    "left_wrist":     _extract_lm(lms, PL.LEFT_WRIST),
                    "right_wrist":    _extract_lm(lms, PL.RIGHT_WRIST),
                    "left_shoulder":  _extract_lm(lms, PL.LEFT_SHOULDER),
                    "right_shoulder": _extract_lm(lms, PL.RIGHT_SHOULDER),
                }
            else:
                fd = {
                    "frame_idx":      raw_idx,
                    "timestamp_ms":   timestamp_ms,
                    "left_wrist":     None,
                    "right_wrist":    None,
                    "left_shoulder":  None,
                    "right_shoulder": None,
                }

            frame_data.append(fd)
            logger.debug(
                "Frame %d (%.0f ms): lw=%s, rw=%s",
                raw_idx, timestamp_ms,
                fd["left_wrist"] is not None,
                fd["right_wrist"] is not None,
            )

            raw_idx += 1

    finally:
        cap.release()

    return frame_data, fps, frame_count, duration_ms


# ---------------------------------------------------------------------------
# Private helpers — velocity & smoothing
# ---------------------------------------------------------------------------

def _wrist_velocities(
    frame_data: list[_FrameData],
) -> tuple[list[float], float, float]:
    """
    Compute per-sampled-frame maximum wrist velocity.

    Velocity is the frame-to-frame Euclidean distance of each wrist in
    normalised coordinates.  Index 0 is always 0.0 (no previous frame).

    Returns:
        vels          – per-frame max wrist velocity
        left_total    – cumulative left-wrist velocity over all frames
        right_total   – cumulative right-wrist velocity over all frames
    """
    n = len(frame_data)
    vels: list[float] = [0.0] * n
    left_total: float = 0.0
    right_total: float = 0.0

    for i in range(1, n):
        prev, curr = frame_data[i - 1], frame_data[i]

        vl = 0.0
        if prev["left_wrist"] and curr["left_wrist"]:
            vl = math.hypot(
                curr["left_wrist"]["x"] - prev["left_wrist"]["x"],
                curr["left_wrist"]["y"] - prev["left_wrist"]["y"],
            )
            left_total += vl

        vr = 0.0
        if prev["right_wrist"] and curr["right_wrist"]:
            vr = math.hypot(
                curr["right_wrist"]["x"] - prev["right_wrist"]["x"],
                curr["right_wrist"]["y"] - prev["right_wrist"]["y"],
            )
            right_total += vr

        vels[i] = max(vl, vr)

    return vels, left_total, right_total


def _rolling_mean(values: list[float], window: int) -> list[float]:
    """Apply a centred rolling mean with edge-clamped boundaries."""
    half = window // 2
    n = len(values)
    result: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result


# ---------------------------------------------------------------------------
# Algorithm 1 — trim window detection
# ---------------------------------------------------------------------------

def _middle_40(duration_ms: int) -> tuple[int, int, bool]:
    """Return the middle 40 % of the video as a low-confidence fallback."""
    if duration_ms <= 0:
        return 0, 0, True
    margin = int(duration_ms * 0.30)
    end = duration_ms - margin
    return margin, end, True


def _detect_trim_window(
    frame_data: list[_FrameData],
    smoothed: list[float],
    duration_ms: int,
) -> tuple[int, int, bool]:
    """
    Locate the throw segment from the smoothed wrist-velocity signal.

    Strategy:
    1. Count high-confidence frames; fall back if too few.
    2. Find the peak energy sample; fall back if too weak.
    3. Expand outward from the peak until energy drops below 20 % of peak.
    4. Pad each side by ``_PAD_MS``, clamped to [0, duration_ms].

    Returns:
        (start_ms, end_ms, low_confidence)
    """
    high_conf = sum(
        1 for fd in frame_data
        if fd["left_wrist"] is not None or fd["right_wrist"] is not None
    )

    if high_conf < _FALLBACK_THRESHOLD:
        logger.warning(
            "Pose confidence too low: only %d/%d frames had wrist detections "
            "(threshold=%d) — using middle-40%% fallback",
            high_conf, len(frame_data), _FALLBACK_THRESHOLD,
        )
        return _middle_40(duration_ms)

    peak_val: float = max(smoothed, default=0.0)

    if peak_val < _MIN_PEAK_ENERGY:
        logger.warning(
            "Peak wrist velocity %.5f is below the motion threshold %.5f — "
            "no clear throw detected; using middle-40%% fallback",
            peak_val, _MIN_PEAK_ENERGY,
        )
        return _middle_40(duration_ms)

    peak_idx: int = smoothed.index(peak_val)
    threshold: float = peak_val * _PEAK_THRESHOLD_RATIO

    # Expand the window leftward from the peak.
    lo = peak_idx
    while lo > 0 and smoothed[lo - 1] >= threshold:
        lo -= 1

    # Expand rightward from the peak.
    hi = peak_idx
    while hi < len(smoothed) - 1 and smoothed[hi + 1] >= threshold:
        hi += 1

    start_ts: float = frame_data[lo]["timestamp_ms"]
    end_ts: float = frame_data[hi]["timestamp_ms"]

    start_ms = max(0, int(start_ts) - _PAD_MS)
    end_ms = min(duration_ms, int(end_ts) + _PAD_MS)

    logger.info(
        "Trim detected: peak=%.4f @ sampled-idx=%d, "
        "raw window=[%.0f–%.0f ms], padded=[%d–%d ms]",
        peak_val, peak_idx, start_ts, end_ts, start_ms, end_ms,
    )
    return start_ms, end_ms, False


# ---------------------------------------------------------------------------
# Algorithm 2 — throw-type classification
# ---------------------------------------------------------------------------

def _classify_throw_type(
    frame_data: list[_FrameData],
    start_ms: float,
    end_ms: float,
    left_vel_total: float,
    right_vel_total: float,
) -> tuple[str, float]:
    """
    Classify the throw as "backhand", "forehand", or "unknown".

    Uses the net signed cross-body wrist displacement within *[start_ms, end_ms]*
    relative to the mid-shoulder horizontal midpoint in normalised coordinates:

    * Positive delta → wrist crossed from non-dominant side to dominant side
      → **backhand**.
    * Negative delta → wrist swung outward away from body centre → **forehand**.

    Dominant hand is inferred from which wrist accumulated more velocity during
    the trim-detection pass.

    Returns:
        (throw_type, confidence)  where throw_type ∈ {"backhand","forehand","unknown"}
        and confidence ∈ [0.0, 1.0].
    """
    window_frames = [
        fd for fd in frame_data
        if start_ms <= fd["timestamp_ms"] <= end_ms
    ]

    if len(window_frames) < 10:
        logger.info(
            "Throw window contains only %d sampled frames — "
            "too few for classification; returning unknown",
            len(window_frames),
        )
        return "unknown", 0.0

    # Identify dominant side by cumulative wrist velocity from the trim pass.
    dominant_side: str = "right" if right_vel_total >= left_vel_total else "left"
    one_wrist_only: bool = False

    dominant_visible = any(
        _get_wrist(fd, dominant_side) is not None for fd in window_frames
    )
    if not dominant_visible:
        alt_side = "left" if dominant_side == "right" else "right"
        alt_visible = any(
            _get_wrist(fd, alt_side) is not None for fd in window_frames
        )
        if not alt_visible:
            logger.info("No wrist landmarks found in throw window — returning unknown")
            return "unknown", 0.0
        logger.info(
            "Dominant wrist (%s) absent in window; using %s wrist "
            "(confidence will be penalised ×%.2f)",
            dominant_side, alt_side, _ONE_WRIST_PENALTY,
        )
        dominant_side = alt_side
        one_wrist_only = True

    # Collect wrist-x relative to mid-shoulder for frames that have all landmarks.
    relative_xs: list[float] = []
    for fd in window_frames:
        wrist = _get_wrist(fd, dominant_side)
        ls = fd["left_shoulder"]
        rs = fd["right_shoulder"]
        if wrist is None or ls is None or rs is None:
            continue
        mid_shoulder_x = (ls["x"] + rs["x"]) / 2.0
        relative_xs.append(wrist["x"] - mid_shoulder_x)

    if len(relative_xs) < 10:
        logger.info(
            "Only %d frames had all required landmarks (wrist + both shoulders) "
            "in the throw window — returning unknown",
            len(relative_xs),
        )
        return "unknown", 0.0

    # Net cross-body travel: positive → backhand, negative → forehand.
    delta: float = relative_xs[-1] - relative_xs[0]
    raw_conf: float = min(abs(delta) / _EXPECTED_MAX_DELTA, 1.0)

    if one_wrist_only:
        raw_conf *= _ONE_WRIST_PENALTY

    logger.debug(
        "Throw-type classification: dominant=%s_wrist, delta=%.4f, "
        "raw_conf=%.3f, one_wrist_only=%s",
        dominant_side, delta, raw_conf, one_wrist_only,
    )

    if abs(delta) < _CROSS_BODY_THRESHOLD or raw_conf < _MIN_THROW_TYPE_CONFIDENCE:
        logger.info(
            "Classification below threshold (|delta|=%.3f < %.3f or "
            "conf=%.3f < %.3f) — returning unknown",
            abs(delta), _CROSS_BODY_THRESHOLD, raw_conf, _MIN_THROW_TYPE_CONFIDENCE,
        )
        return "unknown", raw_conf

    throw_type = "backhand" if delta > 0 else "forehand"
    logger.info(
        "Throw type: %s (delta=%.4f, conf=%.3f)", throw_type, delta, raw_conf
    )
    return throw_type, raw_conf


# ---------------------------------------------------------------------------
# Fallback helper
# ---------------------------------------------------------------------------

def _make_fallback(duration_ms: int) -> dict:
    """Construct a low-confidence middle-40 % result for use without pose data."""
    start_ms, end_ms, _ = _middle_40(duration_ms)
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": duration_ms,
        "low_confidence": True,
        "detected_throw_type": "unknown",
        "throw_type_confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_throw_segment(video_path: Path) -> dict:
    """
    Analyse *video_path* with MediaPipe Pose and identify the throw segment.

    This is a synchronous, CPU-bound function.  The caller must dispatch it
    via ``asyncio.to_thread`` to avoid blocking the event loop::

        result = await asyncio.to_thread(detect_throw_segment, path)

    A single ``mp.solutions.pose.Pose`` context is used for the entire call
    (both algorithms share it).  The object is *never* cached at module level
    because MediaPipe Pose is not thread-safe.

    Returns a dict with keys:
        start_ms              (int)   – throw segment start in ms
        end_ms                (int)   – throw segment end in ms
        duration_ms           (int)   – total video duration in ms
        low_confidence        (bool)  – True when detection confidence is low
        detected_throw_type   (str)   – "backhand" | "forehand" | "unknown"
        throw_type_confidence (float) – confidence score in [0.0, 1.0]
    """
    # Guard against missing optional dependency.
    try:
        import mediapipe as mp
    except ImportError:
        logger.warning(
            "mediapipe is not installed — auto-trim and throw-type detection are "
            "disabled.  Install it with: pip install mediapipe"
        )
        cap = cv2.VideoCapture(str(video_path))
        try:
            fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
            fc: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration_ms_fb: int = int((fc / fps) * 1000)
        finally:
            cap.release()
        return _make_fallback(duration_ms_fb)

    logger.info("detect_throw_segment: processing %s", video_path.name)

    # static_image_mode=True processes each frame independently, which is
    # correct for any stride value and avoids tracking-state corruption when
    # frames are skipped.  model_complexity=0 (Lite) prioritises speed.
    with mp.solutions.pose.Pose(
        static_image_mode=True,
        model_complexity=0,
        smooth_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        frame_data, fps, frame_count, duration_ms = _run_pose_pass(video_path, pose)

    if not frame_data:
        logger.warning("No frames could be read from %s", video_path)
        return _make_fallback(duration_ms)

    # --- Algorithm 1: auto-trim ---
    vels, left_total, right_total = _wrist_velocities(frame_data)
    smoothed = _rolling_mean(vels, _SMOOTH_WINDOW)

    start_ms, end_ms, low_confidence = _detect_trim_window(
        frame_data, smoothed, duration_ms
    )

    # --- Algorithm 2: throw-type (reuses frame_data from Algorithm 1) ---
    throw_type, confidence = _classify_throw_type(
        frame_data, float(start_ms), float(end_ms), left_total, right_total
    )

    logger.info(
        "detect_throw_segment complete: window=[%d–%d ms] / %d ms, "
        "low_confidence=%s, throw_type=%s (conf=%.3f)",
        start_ms, end_ms, duration_ms, low_confidence, throw_type, confidence,
    )

    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": duration_ms,
        "low_confidence": low_confidence,
        "detected_throw_type": throw_type,
        "throw_type_confidence": confidence,
    }
