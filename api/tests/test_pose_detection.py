"""
Unit tests for api/services/pose_detection.py.

All tests use synthetic or mocked data — no real video files, no real
MediaPipe or OpenCV calls are required.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from services.pose_detection import (
    _classify_throw_type,
    _detect_trim_window,
    _extract_lm,
    _get_wrist,
    _make_fallback,
    _middle_40,
    _rolling_mean,
    _run_pose_pass,
    _wrist_velocities,
    detect_throw_segment,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _lm(x: float = 0.5, y: float = 0.5, v: float = 0.9) -> dict:
    return {"x": x, "y": y, "v": v}


def _make_fd(
    ts: float = 0.0,
    lw=None,
    rw=None,
    ls=None,
    rs=None,
) -> dict:
    return {
        "frame_idx": int(ts),
        "timestamp_ms": float(ts),
        "left_wrist": lw,
        "right_wrist": rw,
        "left_shoulder": ls,
        "right_shoulder": rs,
    }


def _mock_lm_obj(x: float, y: float, visibility: float) -> MagicMock:
    m = MagicMock()
    m.x = x
    m.y = y
    m.visibility = visibility
    return m


def _mock_landmarks_obj(lm_map: dict) -> MagicMock:
    """Return a fake MediaPipe PoseLandmarks object backed by *lm_map* (dict)."""
    lms = MagicMock()
    lms.landmark = lm_map  # plain dict; lms.landmark[idx] works directly
    return lms


# ---------------------------------------------------------------------------
# _extract_lm
# ---------------------------------------------------------------------------

class TestExtractLm:
    def test_returns_none_when_visibility_strictly_below_threshold(self):
        lms = _mock_landmarks_obj({3: _mock_lm_obj(0.3, 0.4, 0.49)})
        assert _extract_lm(lms, 3) is None

    def test_returns_none_when_visibility_is_zero(self):
        lms = _mock_landmarks_obj({0: _mock_lm_obj(0.5, 0.5, 0.0)})
        assert _extract_lm(lms, 0) is None

    def test_returns_dict_when_visibility_exactly_at_threshold(self):
        lms = _mock_landmarks_obj({7: _mock_lm_obj(0.3, 0.4, 0.5)})
        assert _extract_lm(lms, 7) == {"x": 0.3, "y": 0.4, "v": 0.5}

    def test_returns_dict_when_visibility_above_threshold(self):
        lms = _mock_landmarks_obj({1: _mock_lm_obj(0.6, 0.7, 0.95)})
        assert _extract_lm(lms, 1) == {"x": 0.6, "y": 0.7, "v": 0.95}


# ---------------------------------------------------------------------------
# _get_wrist
# ---------------------------------------------------------------------------

class TestGetWrist:
    def test_returns_left_wrist(self):
        fd = _make_fd(0, lw=_lm(0.1), rw=_lm(0.8))
        assert _get_wrist(fd, "left") == {"x": 0.1, "y": 0.5, "v": 0.9}

    def test_returns_right_wrist(self):
        fd = _make_fd(0, lw=_lm(0.1), rw=_lm(0.8))
        assert _get_wrist(fd, "right") == {"x": 0.8, "y": 0.5, "v": 0.9}

    def test_returns_none_when_wrist_absent(self):
        fd = _make_fd(0)
        assert _get_wrist(fd, "left") is None
        assert _get_wrist(fd, "right") is None


# ---------------------------------------------------------------------------
# _wrist_velocities
# ---------------------------------------------------------------------------

class TestWristVelocities:
    def test_empty_list(self):
        vels, lt, rt = _wrist_velocities([])
        assert vels == []
        assert lt == 0.0
        assert rt == 0.0

    def test_single_frame_returns_zero(self):
        frames = [_make_fd(0, lw=_lm(0.5), rw=_lm(0.6))]
        vels, lt, rt = _wrist_velocities(frames)
        assert vels == [0.0]
        assert lt == 0.0
        assert rt == 0.0

    def test_right_wrist_horizontal_movement(self):
        frames = [
            _make_fd(0, rw=_lm(0.5)),
            _make_fd(100, rw=_lm(0.8)),  # Δx = 0.3
        ]
        vels, lt, rt = _wrist_velocities(frames)
        assert vels[0] == 0.0
        assert abs(vels[1] - 0.3) < 1e-9
        assert lt == 0.0
        assert abs(rt - 0.3) < 1e-9

    def test_left_wrist_vertical_movement(self):
        frames = [
            _make_fd(0, lw=_lm(0.2, 0.5)),
            _make_fd(100, lw=_lm(0.2, 0.8)),  # Δy = 0.3
        ]
        vels, lt, rt = _wrist_velocities(frames)
        assert abs(vels[1] - 0.3) < 1e-9
        assert abs(lt - 0.3) < 1e-9
        assert rt == 0.0

    def test_max_of_both_wrists_is_used(self):
        frames = [
            _make_fd(0, lw=_lm(0.2, 0.2), rw=_lm(0.8, 0.2)),
            _make_fd(100, lw=_lm(0.3, 0.2), rw=_lm(0.5, 0.2)),
        ]
        vels, lt, rt = _wrist_velocities(frames)
        vl = math.hypot(0.1, 0.0)
        vr = math.hypot(0.3, 0.0)
        assert abs(vels[1] - max(vl, vr)) < 1e-9

    def test_none_wrists_produce_zero_velocity(self):
        frames = [_make_fd(0), _make_fd(100)]
        vels, lt, rt = _wrist_velocities(frames)
        assert vels == [0.0, 0.0]
        assert lt == 0.0
        assert rt == 0.0


# ---------------------------------------------------------------------------
# _rolling_mean
# ---------------------------------------------------------------------------

class TestRollingMean:
    def test_empty_list(self):
        assert _rolling_mean([], 3) == []

    def test_single_element(self):
        assert _rolling_mean([5.0], 7) == [5.0]

    def test_window_larger_than_list_averages_all(self):
        result = _rolling_mean([1.0, 2.0, 3.0], 10)
        assert all(abs(v - 2.0) < 1e-9 for v in result)

    def test_window_3_centre_element(self):
        values = [0.0, 0.0, 1.0, 0.0, 0.0]
        result = _rolling_mean(values, 3)
        # Centre element: window over indices 1-3 → (0+1+0)/3
        assert result[2] == pytest.approx(1.0 / 3.0)

    def test_uniform_values_unchanged(self):
        values = [3.0] * 10
        result = _rolling_mean(values, 5)
        assert all(abs(v - 3.0) < 1e-9 for v in result)


# ---------------------------------------------------------------------------
# _middle_40
# ---------------------------------------------------------------------------

class TestMiddle40:
    def test_normal_duration(self):
        start, end, low_conf = _middle_40(10_000)
        assert start == 3_000  # 30 %
        assert end == 7_000    # 70 %
        assert low_conf is True

    def test_zero_duration(self):
        start, end, low_conf = _middle_40(0)
        assert start == 0
        assert end == 0  # both clamped to 0 for a zero-duration video
        assert low_conf is True

    def test_small_duration(self):
        start, end, low_conf = _middle_40(100)
        assert start == 30
        assert end == 70
        assert low_conf is True


# ---------------------------------------------------------------------------
# _detect_trim_window
# ---------------------------------------------------------------------------

class TestDetectTrimWindow:
    @staticmethod
    def _frames_with_wrists(n: int, step: float = 100.0) -> list:
        return [_make_fd(i * step, lw=_lm(0.3), rw=_lm(0.7)) for i in range(n)]

    @staticmethod
    def _frames_no_wrists(n: int, step: float = 100.0) -> list:
        return [_make_fd(i * step) for i in range(n)]

    def test_too_few_high_conf_frames_returns_fallback(self):
        frames = self._frames_no_wrists(5)  # 5 < _FALLBACK_THRESHOLD (10)
        _, _, low_conf = _detect_trim_window(frames, [0.01] * 5, 5_000)
        assert low_conf is True

    def test_peak_below_energy_threshold_returns_fallback(self):
        frames = self._frames_with_wrists(20)
        # all values below _MIN_PEAK_ENERGY (0.005)
        smoothed = [0.001] * 20
        _, _, low_conf = _detect_trim_window(frames, smoothed, 2_000)
        assert low_conf is True

    def test_clear_peak_returns_low_confidence_false(self):
        n = 30
        frames = self._frames_with_wrists(n, 100.0)
        smoothed = [0.001] * n
        smoothed[15] = 0.10  # strong peak in the middle
        start, end, low_conf = _detect_trim_window(frames, smoothed, 3_000)
        assert low_conf is False
        assert end > start

    def test_padding_start_clamped_at_zero(self):
        n = 20
        frames = self._frames_with_wrists(n, 100.0)
        smoothed = [0.001] * n
        smoothed[0] = 0.10  # peak at very first frame → start would be negative
        start, _, _ = _detect_trim_window(frames, smoothed, 2_000)
        assert start == 0

    def test_padding_end_clamped_at_duration(self):
        n = 20
        duration_ms = 1_900  # just under (n-1)*100 + _PAD_MS
        frames = self._frames_with_wrists(n, 100.0)
        smoothed = [0.001] * n
        smoothed[n - 1] = 0.10  # peak at last frame → end would exceed duration
        _, end, _ = _detect_trim_window(frames, smoothed, duration_ms)
        assert end <= duration_ms


# ---------------------------------------------------------------------------
# _classify_throw_type
# ---------------------------------------------------------------------------

class TestClassifyThrowType:
    @staticmethod
    def _build_frames(n: int, start_x: float, end_x: float, side: str = "right") -> list:
        """Build n frames where the named wrist moves linearly from start_x to end_x."""
        frames = []
        for i in range(n):
            t = i / max(n - 1, 1)
            wx = start_x + (end_x - start_x) * t
            rw = {"x": wx, "y": 0.5, "v": 0.95} if side == "right" else None
            lw = {"x": wx, "y": 0.5, "v": 0.95} if side == "left" else None
            frames.append(_make_fd(
                float(i * 100),
                lw=lw,
                rw=rw,
                ls={"x": 0.3, "y": 0.8, "v": 0.95},
                rs={"x": 0.7, "y": 0.8, "v": 0.95},
            ))
        return frames

    def test_too_few_window_frames_returns_unknown(self):
        frames = self._build_frames(5, 0.1, 0.9)  # 5 < 10
        throw_type, conf = _classify_throw_type(frames, 0.0, 400.0, 0.0, 1.0)
        assert throw_type == "unknown"
        assert conf == 0.0

    def test_no_wrist_landmarks_returns_unknown(self):
        frames = [_make_fd(float(i * 100)) for i in range(20)]
        throw_type, conf = _classify_throw_type(frames, 0.0, 1900.0, 0.0, 0.0)
        assert throw_type == "unknown"
        assert conf == 0.0

    def test_classifies_backhand_positive_delta(self):
        # Right wrist: 0.1 → 0.9.  relative to shoulder mid (0.5): -0.4 → +0.4.
        # delta = 0.8 > cross_body_threshold (0.25).  conf = min(0.8/0.6, 1) = 1.0.
        frames = self._build_frames(20, 0.1, 0.9, side="right")
        throw_type, conf = _classify_throw_type(frames, 0.0, 1900.0, 0.0, 1.0)
        assert throw_type == "backhand"
        assert conf > 0.0

    def test_classifies_forehand_negative_delta(self):
        # Right wrist: 0.9 → 0.1.  delta = -0.8 < 0.
        frames = self._build_frames(20, 0.9, 0.1, side="right")
        throw_type, conf = _classify_throw_type(frames, 0.0, 1900.0, 0.0, 1.0)
        assert throw_type == "forehand"
        assert conf > 0.0

    def test_unknown_when_delta_too_small(self):
        # Wrist barely moves: delta ≈ 0.019 < _CROSS_BODY_THRESHOLD (0.25).
        n = 20
        frames = [
            _make_fd(
                float(i * 100),
                rw={"x": 0.5 + i * 0.001, "y": 0.5, "v": 0.95},
                ls={"x": 0.3, "y": 0.8, "v": 0.95},
                rs={"x": 0.7, "y": 0.8, "v": 0.95},
            )
            for i in range(n)
        ]
        throw_type, _ = _classify_throw_type(frames, 0.0, 1900.0, 0.0, 1.0)
        assert throw_type == "unknown"

    def test_dominant_absent_alt_wrist_classifies_with_penalty(self):
        """When dominant (right) wrist is absent, left wrist used with ×0.80 penalty."""
        # Left wrist: 0.1 → 0.9.  delta=0.8.  conf=1.0*0.80=0.80 ≥ 0.70 → backhand.
        n = 20
        frames = []
        for i in range(n):
            t = i / (n - 1)
            wx = 0.1 + 0.8 * t
            frames.append(_make_fd(
                float(i * 100),
                lw={"x": wx, "y": 0.5, "v": 0.95},
                rw=None,  # dominant side absent
                ls={"x": 0.3, "y": 0.8, "v": 0.95},
                rs={"x": 0.7, "y": 0.8, "v": 0.95},
            ))
        # right_vel_total=2.0 → dominant=right; but right wrist is absent
        throw_type, conf = _classify_throw_type(
            frames, 0.0, float(n * 100), 0.0, 2.0
        )
        assert throw_type == "backhand"
        assert conf == pytest.approx(0.80, rel=0.05)

    def test_unknown_when_confidence_below_threshold(self):
        """Returns 'unknown' when delta is OK but confidence is below 0.70."""
        # Right wrist: 0.35 → 0.65.  delta_rel = (0.65-0.5)-(0.35-0.5) = 0.30.
        # abs(0.30) ≥ cross_body_threshold (0.25) — delta OK.
        # conf = min(0.30/0.60, 1.0) = 0.50 < min_throw_type_confidence (0.70) → unknown.
        n = 20
        frames = [
            _make_fd(
                float(i * 100),
                rw={"x": 0.35 + i * (0.30 / (n - 1)), "y": 0.5, "v": 0.95},
                ls={"x": 0.3, "y": 0.8, "v": 0.95},
                rs={"x": 0.7, "y": 0.8, "v": 0.95},
            )
            for i in range(n)
        ]
        throw_type, _ = _classify_throw_type(frames, 0.0, 1900.0, 0.0, 1.0)
        assert throw_type == "unknown"

    def test_few_complete_frames_in_window_returns_unknown(self):
        """Returns 'unknown' when < 10 frames have wrist + both shoulders."""
        n = 20
        frames = []
        for i in range(n):
            # Only first 5 frames have the right wrist; rest are missing it
            rw = {"x": 0.5 + i * 0.05, "y": 0.5, "v": 0.95} if i < 5 else None
            frames.append(_make_fd(
                float(i * 100),
                rw=rw,
                ls={"x": 0.3, "y": 0.8, "v": 0.95},
                rs={"x": 0.7, "y": 0.8, "v": 0.95},
            ))
        # 5 complete frames < 10 required → unknown
        throw_type, _ = _classify_throw_type(frames, 0.0, 1900.0, 0.0, 1.0)
        assert throw_type == "unknown"


# ---------------------------------------------------------------------------
# _make_fallback
# ---------------------------------------------------------------------------

class TestMakeFallback:
    def test_correct_structure_normal_duration(self):
        result = _make_fallback(10_000)
        assert result["low_confidence"] is True
        assert result["detected_throw_type"] == "unknown"
        assert result["throw_type_confidence"] == 0.0
        assert result["duration_ms"] == 10_000
        assert result["start_ms"] == 3_000
        assert result["end_ms"] == 7_000

    def test_zero_duration(self):
        result = _make_fallback(0)
        assert result["low_confidence"] is True
        assert result["start_ms"] == 0
        assert result["end_ms"] == 0  # _middle_40 clamps both to 0 for zero-duration


# ---------------------------------------------------------------------------
# _run_pose_pass
# ---------------------------------------------------------------------------

class TestRunPosePass:
    @staticmethod
    def _make_mock_cv2(bgr_frame, *, fps: float = 30.0, frame_count: float = 30.0):
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.get.side_effect = [fps, frame_count]
        mock_cap.read.side_effect = [(True, bgr_frame), (False, None)]
        mock_cv2.cvtColor.return_value = bgr_frame
        return mock_cv2, mock_cap

    @staticmethod
    def _make_mock_mp():
        mock_mp = MagicMock()
        mock_mp.solutions.pose.PoseLandmark = MagicMock()
        return mock_mp

    def test_single_frame_no_landmarks(self):
        """Processes one frame when pose returns no landmarks."""
        fake_bgr = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_mp = self._make_mock_mp()
        mock_cv2, _ = self._make_mock_cv2(fake_bgr)

        mock_result = MagicMock()
        mock_result.pose_landmarks = None
        mock_pose_ctx = MagicMock()
        mock_pose_ctx.process.return_value = mock_result

        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch("services.pose_detection.cv2", mock_cv2):
                frames, fps, frame_count, duration_ms = _run_pose_pass(
                    Path("/tmp/test.mp4"), mock_pose_ctx
                )

        assert len(frames) == 1
        assert fps == 30.0
        assert frames[0]["left_wrist"] is None
        assert frames[0]["right_wrist"] is None

    def test_single_frame_with_landmarks_extracted(self):
        """Extracts all four landmarks when pose detection succeeds."""
        fake_bgr = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_mp = self._make_mock_mp()
        # Assign integer values so _extract_lm can index with them
        mock_mp.solutions.pose.PoseLandmark.LEFT_WRIST = 15
        mock_mp.solutions.pose.PoseLandmark.RIGHT_WRIST = 16
        mock_mp.solutions.pose.PoseLandmark.LEFT_SHOULDER = 11
        mock_mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER = 12

        landmark_map = {
            15: _mock_lm_obj(0.4, 0.6, 0.9),   # LEFT_WRIST
            16: _mock_lm_obj(0.6, 0.6, 0.9),   # RIGHT_WRIST
            11: _mock_lm_obj(0.3, 0.4, 0.9),   # LEFT_SHOULDER
            12: _mock_lm_obj(0.7, 0.4, 0.9),   # RIGHT_SHOULDER
        }
        fake_lms = _mock_landmarks_obj(landmark_map)

        mock_result = MagicMock()
        mock_result.pose_landmarks = fake_lms
        mock_pose_ctx = MagicMock()
        mock_pose_ctx.process.return_value = mock_result

        mock_cv2, _ = self._make_mock_cv2(fake_bgr)

        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch("services.pose_detection.cv2", mock_cv2):
                frames, _, _, _ = _run_pose_pass(
                    Path("/tmp/test.mp4"), mock_pose_ctx
                )

        assert len(frames) == 1
        assert frames[0]["right_wrist"] == {"x": 0.6, "y": 0.6, "v": 0.9}
        assert frames[0]["left_wrist"] == {"x": 0.4, "y": 0.6, "v": 0.9}
        assert frames[0]["left_shoulder"] == {"x": 0.3, "y": 0.4, "v": 0.9}
        assert frames[0]["right_shoulder"] == {"x": 0.7, "y": 0.4, "v": 0.9}

    def test_wide_frame_triggers_resize(self):
        """Frames wider than 640 px are resized before being sent to MediaPipe."""
        fake_bgr = np.zeros((480, 1280, 3), dtype=np.uint8)   # w=1280 > 640
        resized = np.zeros((240, 640, 3), dtype=np.uint8)
        mock_mp = self._make_mock_mp()

        mock_result = MagicMock()
        mock_result.pose_landmarks = None
        mock_pose_ctx = MagicMock()
        mock_pose_ctx.process.return_value = mock_result

        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.get.side_effect = [30.0, 30.0]
        mock_cap.read.side_effect = [(True, fake_bgr), (False, None)]
        mock_cv2.resize.return_value = resized
        mock_cv2.cvtColor.return_value = resized

        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch("services.pose_detection.cv2", mock_cv2):
                frames, _, _, _ = _run_pose_pass(
                    Path("/tmp/test.mp4"), mock_pose_ctx
                )

        mock_cv2.resize.assert_called_once()
        assert len(frames) == 1

    def test_stride_uses_grab_for_skipped_frames(self):
        """With stride > 1, cap.grab() is called for non-sampled frames."""
        fake_bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_mp = self._make_mock_mp()

        mock_result = MagicMock()
        mock_result.pose_landmarks = None
        mock_pose_ctx = MagicMock()
        mock_pose_ctx.process.return_value = mock_result

        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        # fps=10, frame_count=1200 → stride = max(1, 1200//600) = 2
        mock_cap.get.side_effect = [10.0, 1200.0]
        # Frame 0 sampled; frame 1 grab; frame 2 read→False (end of video)
        mock_cap.read.side_effect = [(True, fake_bgr), (False, None)]
        mock_cap.grab.return_value = True
        mock_cv2.cvtColor.return_value = fake_bgr

        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch("services.pose_detection.cv2", mock_cv2):
                frames, fps, _, _ = _run_pose_pass(
                    Path("/tmp/test.mp4"), mock_pose_ctx
                )

        assert fps == 10.0
        assert mock_cap.grab.called


# ---------------------------------------------------------------------------
# detect_throw_segment — public API
# ---------------------------------------------------------------------------

class TestDetectThrowSegment:
    @staticmethod
    def _make_mock_mp():
        mock_mp = MagicMock()
        mock_pose_instance = MagicMock()
        mock_mp.solutions.pose.Pose.return_value.__enter__ = MagicMock(
            return_value=mock_pose_instance
        )
        mock_mp.solutions.pose.Pose.return_value.__exit__ = MagicMock(
            return_value=False
        )
        return mock_mp

    def test_import_error_returns_fallback(self):
        """When mediapipe is absent the function returns a low-confidence fallback."""
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.get.side_effect = [30.0, 300.0]  # fps, frame_count

        with patch.dict(sys.modules, {"mediapipe": None}):
            with patch("services.pose_detection.cv2", mock_cv2):
                result = detect_throw_segment(Path("/tmp/test.mp4"))

        assert result["low_confidence"] is True
        assert result["detected_throw_type"] == "unknown"
        assert result["throw_type_confidence"] == 0.0

    def test_empty_frame_data_returns_fallback(self):
        """When no frames are decoded, return a low-confidence fallback with real duration."""
        mock_mp = self._make_mock_mp()

        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch(
                "services.pose_detection._run_pose_pass",
                return_value=([], 30.0, 300, 10_000),
            ):
                result = detect_throw_segment(Path("/tmp/test.mp4"))

        assert result["low_confidence"] is True
        assert result["duration_ms"] == 10_000
        assert result["start_ms"] == 3_000
        assert result["end_ms"] == 7_000

    def test_normal_backhand_path_returns_correct_keys_and_type(self):
        """Full happy-path: synthetic backhand frames → 'backhand'."""
        n = 40
        step = 100.0
        duration_ms = int(n * step)

        # Right wrist moves steadily from x=0.1 to x=0.8; shoulders fixed.
        frames = []
        for i in range(n):
            t = i / (n - 1)
            wx = 0.1 + 0.7 * t
            frames.append({
                "frame_idx": i,
                "timestamp_ms": float(i * step),
                "left_wrist": None,
                "right_wrist": {"x": wx, "y": 0.5, "v": 0.95},
                "left_shoulder": {"x": 0.3, "y": 0.8, "v": 0.95},
                "right_shoulder": {"x": 0.7, "y": 0.8, "v": 0.95},
            })

        mock_mp = self._make_mock_mp()
        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch(
                "services.pose_detection._run_pose_pass",
                return_value=(frames, 10.0, n, duration_ms),
            ):
                result = detect_throw_segment(Path("/tmp/test.mp4"))

        for key in ("start_ms", "end_ms", "duration_ms",
                    "low_confidence", "detected_throw_type", "throw_type_confidence"):
            assert key in result
        assert result["detected_throw_type"] == "backhand"

    def test_few_wrist_frames_returns_low_confidence(self):
        """Frames with no wrist detections → low_confidence True."""
        # 5 frames, none with wrist data → high_conf < threshold → fallback
        frames = [_make_fd(float(i * 100)) for i in range(5)]
        mock_mp = self._make_mock_mp()

        with patch.dict(sys.modules, {"mediapipe": mock_mp}):
            with patch(
                "services.pose_detection._run_pose_pass",
                return_value=(frames, 30.0, 5, 500),
            ):
                result = detect_throw_segment(Path("/tmp/test.mp4"))

        assert result["low_confidence"] is True
