import logging
import threading
import types
from pathlib import Path

import cv2
import mediapipe as mp

logger = logging.getLogger(__name__)

_THROW_TYPE_CONFIDENCE_THRESHOLD: float = 0.70
_CROSS_BODY_DELTA_THRESHOLD: float = 0.25
_MIN_POSE_FRAMES: int = 10
_POSE_MIN_VISIBILITY: float = 0.5
# Maximum expected signed delta (normalised units); used to scale confidence to [0, 1].
_DELTA_SCALE: float = 0.5
# Sample ~6 fps; multiplied by actual fps in _run_wrist_classification.
_SAMPLE_FPS: int = 6

# Immutable sentinel — safe to return from multiple code paths without risk of mutation.
_UNKNOWN_THROW: types.MappingProxyType = types.MappingProxyType(
    {"detected_throw_type": "unknown", "throw_type_confidence": 0.0}
)

# Thread-local MediaPipe Pose instances — one model per thread-pool worker, amortised
# across requests so the model is not loaded from disk on every upload.
_pose_tls: threading.local = threading.local()


def _get_pose() -> "mp.solutions.pose.Pose":  # type: ignore[name-defined]
    """Return a cached mp.solutions.pose.Pose for the current thread."""
    if not hasattr(_pose_tls, "pose"):
        mp_pose = mp.solutions.pose  # type: ignore[attr-defined]
        _pose_tls.pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _pose_tls.pose  # type: ignore[return-value]


def detect_throw_segment(video_path: Path) -> dict:
    """
    Analyse *video_path* with MediaPipe Pose and identify the disc-golf throw segment.

    Returns a dict with keys:
        start_ms               (int)   – detected throw start in milliseconds
        end_ms                 (int)   – detected throw end in milliseconds
        duration_ms            (int)   – total video duration in milliseconds
        low_confidence         (bool)  – True when trim detection heuristic is uncertain
        detected_throw_type    (str)   – 'backhand' | 'forehand' | 'unknown'
        throw_type_confidence  (float) – classification confidence in [0.0, 1.0]
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration_ms = int((frame_count / fps) * 1000)
    finally:
        cap.release()

    logger.info(
        "detect_throw_segment: duration=%dms (stub — returning full clip, low_confidence=True)",
        duration_ms,
    )

    start_ms = 0
    end_ms = duration_ms

    # Pass fps so _classify_throw_type does not need to re-read FPS/metadata from the file
    # (it may still open the video again for frame sampling).
    throw_type_result = _classify_throw_type(video_path, start_ms, end_ms, fps)

    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": duration_ms,
        "low_confidence": True,
        **throw_type_result,
    }


def _classify_throw_type(
    video_path: Path, start_ms: int, end_ms: int, fps: float
) -> dict:
    """
    Classify backhand vs. forehand using lateral wrist cross-body displacement.

    Returns dict with keys:
        detected_throw_type    (str)   – 'backhand' | 'forehand' | 'unknown'
        throw_type_confidence  (float) – in [0.0, 1.0]
    """
    try:
        return _run_wrist_classification(video_path, start_ms, end_ms, fps)
    except Exception:
        logger.exception("_classify_throw_type: unexpected error; returning unknown")
        return dict(_UNKNOWN_THROW)


def _run_wrist_classification(
    video_path: Path, start_ms: int, end_ms: int, fps: float
) -> dict:
    """Run MediaPipe Pose over the throw window at ~_SAMPLE_FPS and collect observations."""
    mp_pose = mp.solutions.pose  # type: ignore[attr-defined]

    start_frame = int((start_ms / 1000.0) * fps)
    end_frame = int((end_ms / 1000.0) * fps)

    if end_frame <= start_frame:
        return dict(_UNKNOWN_THROW)

    # Stride so at most ~_SAMPLE_FPS frames per second are processed.
    # This caps inference cost regardless of clip length or source frame rate.
    stride = max(1, round(fps / _SAMPLE_FPS))
    logger.info(
        "_run_wrist_classification: frames %d–%d stride=%d (~%d samples)",
        start_frame,
        end_frame,
        stride,
        (end_frame - start_frame) // stride + 1,
    )

    # Each entry: (left_wrist_x, right_wrist_x, mid_shoulder_x)
    observations: list[tuple[float, float, float]] = []

    pose = _get_pose()
    cap = cv2.VideoCapture(str(video_path))
    try:
        frame_idx = start_frame
        while frame_idx <= end_frame:
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_idx))
            ret, frame = cap.read()
            if not ret:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(frame_rgb)

            if not results.pose_landmarks:
                frame_idx += stride
                continue

            lm = results.pose_landmarks.landmark
            left_wrist = lm[mp_pose.PoseLandmark.LEFT_WRIST]
            right_wrist = lm[mp_pose.PoseLandmark.RIGHT_WRIST]
            left_shoulder = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]

            min_vis = min(
                left_wrist.visibility,
                right_wrist.visibility,
                left_shoulder.visibility,
                right_shoulder.visibility,
            )
            if min_vis >= _POSE_MIN_VISIBILITY:
                mid_shoulder_x = (left_shoulder.x + right_shoulder.x) / 2.0
                observations.append((left_wrist.x, right_wrist.x, mid_shoulder_x))

            frame_idx += stride
    finally:
        cap.release()

    return _classify_from_observations(observations)


def _classify_from_observations(
    observations: list[tuple[float, float, float]],
) -> dict:
    """Compute throw-type from collected (left_wrist_x, right_wrist_x, mid_shoulder_x) frames."""
    if len(observations) < _MIN_POSE_FRAMES:
        logger.info(
            "_classify_from_observations: %d high-confidence frames (need %d); returning unknown",
            len(observations),
            _MIN_POSE_FRAMES,
        )
        return dict(_UNKNOWN_THROW)

    # Determine the dominant (throwing) wrist by total frame-to-frame displacement.
    left_disp = sum(
        abs(observations[i][0] - observations[i - 1][0])
        for i in range(1, len(observations))
    )
    right_disp = sum(
        abs(observations[i][1] - observations[i - 1][1])
        for i in range(1, len(observations))
    )
    # wrist_idx: 0 = left_wrist_x, 1 = right_wrist_x
    wrist_idx = 0 if left_disp >= right_disp else 1

    # Wrist offset from mid-shoulder center at first and last high-confidence frames.
    first_wrist_x, _, first_mid_x = observations[0][wrist_idx], None, observations[0][2]
    first_wrist_x = observations[0][wrist_idx]
    first_offset = first_wrist_x - first_mid_x

    last_wrist_x = observations[-1][wrist_idx]
    last_mid_x = observations[-1][2]
    last_offset = last_wrist_x - last_mid_x

    # Positive delta → wrist moved past mid-shoulder line (backhand cross-body motion)
    # Negative delta → wrist swung outward away from center (forehand pendulum motion)
    delta = last_offset - first_offset
    confidence = round(min(abs(delta) / _DELTA_SCALE, 1.0), 3)

    if abs(delta) < _CROSS_BODY_DELTA_THRESHOLD:
        logger.info(
            "_classify_from_observations: |delta|=%.3f below threshold %.3f (conf=%.3f); unknown",
            abs(delta),
            _CROSS_BODY_DELTA_THRESHOLD,
            confidence,
        )
        return {"detected_throw_type": "unknown", "throw_type_confidence": confidence}

    if confidence < _THROW_TYPE_CONFIDENCE_THRESHOLD:
        logger.info(
            "_classify_from_observations: confidence=%.3f below threshold %.2f; unknown",
            confidence,
            _THROW_TYPE_CONFIDENCE_THRESHOLD,
        )
        return {"detected_throw_type": "unknown", "throw_type_confidence": confidence}

    throw_type = "backhand" if delta > 0 else "forehand"
    logger.info(
        "_classify_from_observations: detected=%s confidence=%.3f delta=%.3f",
        throw_type,
        confidence,
        delta,
    )
    return {"detected_throw_type": throw_type, "throw_type_confidence": confidence}
