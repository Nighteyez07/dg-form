"""
Unit tests for the _annotate_frames_with_critique helper in routers.analyze
and the TrimRange max-duration validation rule in models.schemas.
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from models.schemas import CritiqueResponse, ThrowPhase, TrimRange
from routers.analyze import _annotate_frames_with_critique


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_critique(**kwargs) -> CritiqueResponse:
    defaults: dict = {
        "overall_score": "7/10",
        "summary": "Decent throw.",
        "throw_type": "unknown",
        "camera_perspective": "unknown",
        "phases": [],
        "key_focus": "Follow through",
    }
    defaults.update(kwargs)
    return CritiqueResponse(**defaults)


# ---------------------------------------------------------------------------
# _annotate_frames_with_critique
# ---------------------------------------------------------------------------


def test_annotate_frames_empty_returns_empty():
    result = _annotate_frames_with_critique([], _make_critique())
    assert result == []


def test_annotate_frames_applies_label_to_closest_frame():
    """Phase at 600 ms should annotate the frame at 500 ms (closest), not 0 or 1000."""
    frames = [(0, b"frame0"), (500, b"frame1"), (1000, b"frame2")]
    phase = ThrowPhase(
        name="Release",
        timestamp_ms=600,
        observations=["Good snap"],
        recommendations=[],
    )
    critique = _make_critique(phases=[phase])

    with patch(
        "routers.analyze.annotation.annotate_frame", return_value=b"annotated"
    ) as mock_ann:
        result = _annotate_frames_with_critique(frames, critique)

    assert mock_ann.call_count == 1
    # First positional arg is the frame bytes
    assert mock_ann.call_args[0][0] == b"frame1"
    assert result[0][1] == b"frame0"
    assert result[1][1] == b"annotated"
    assert result[2][1] == b"frame2"


def test_annotate_frames_label_truncated_to_80():
    """Labels longer than 80 chars must be sliced before being passed to annotate_frame."""
    frames = [(0, b"frame0")]
    phase = ThrowPhase(
        name="X" * 50,
        timestamp_ms=0,
        observations=["Y" * 50],
        recommendations=[],
    )
    critique = _make_critique(phases=[phase])

    captured: list[str] = []

    def _capture(frame_bytes: bytes, label: str) -> bytes:
        captured.append(label)
        return b"annotated"

    with patch("routers.analyze.annotation.annotate_frame", side_effect=_capture):
        _annotate_frames_with_critique(frames, critique)

    assert len(captured) == 1
    assert len(captured[0]) <= 80


# ---------------------------------------------------------------------------
# TrimRange max-duration validation (schemas.py line 17)
# ---------------------------------------------------------------------------


def test_trim_range_max_duration_raises():
    with pytest.raises(ValidationError):
        TrimRange(start_ms=0, end_ms=30_001)


def test_trim_range_at_max_duration_valid():
    trim = TrimRange(start_ms=0, end_ms=30_000)
    assert trim.end_ms - trim.start_ms == 30_000
