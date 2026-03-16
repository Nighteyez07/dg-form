"""
Unit tests for services.annotation.annotate_frame.

Real cv2 calls are used here — no mocking — because the function is purely
in-memory image processing with no external I/O.
"""

import cv2
import numpy as np
import pytest

from services.annotation import annotate_frame


def _make_test_jpeg(width: int = 100, height: int = 80) -> bytes:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


def test_annotate_frame_returns_bytes():
    jpeg = _make_test_jpeg()
    result = annotate_frame(jpeg, "Test Label")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_annotate_frame_corrupt_input_raises():
    with pytest.raises(ValueError, match="could not decode frame bytes"):
        annotate_frame(b"\x00\x00\x00\x00", "label")


def test_annotate_frame_long_label_truncated_externally():
    """An 80-char label is the caller's responsibility to clip; the function must not crash."""
    jpeg = _make_test_jpeg()
    long_label = "X" * 80
    result = annotate_frame(jpeg, long_label)
    assert isinstance(result, bytes)
    assert len(result) > 0
