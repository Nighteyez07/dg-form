"""
Unit tests for services.video_pipeline and services.openai_client.

All external I/O (ffmpeg, cv2.VideoCapture, openai.OpenAI) is mocked so
these tests run without any real files, processes, or network calls.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.schemas import CritiqueResponse
from services.openai_client import analyze_frames
from services.video_pipeline import (
    assemble_annotated_clip,
    clip_video,
    extract_frames,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CRITIQUE_JSON = json.dumps(
    {
        "overall_score": "8/10",
        "summary": "Good form.",
        "throw_type": "backhand",
        "phases": [],
        "key_focus": "Follow through",
    }
)


def _make_ffmpeg_chain_mock(mock_ffmpeg: MagicMock) -> MagicMock:
    """Wire up the fluent ffmpeg chain and return the terminal process mock."""
    process_mock = MagicMock()
    (
        mock_ffmpeg
        .input.return_value
        .output.return_value
        .overwrite_output.return_value
        .run_async.return_value
    ) = process_mock
    return process_mock


# ---------------------------------------------------------------------------
# video_pipeline — clip_video
# ---------------------------------------------------------------------------


def test_clip_video_calls_ffmpeg():
    with patch("services.video_pipeline.ffmpeg") as mock_ffmpeg:
        process_mock = _make_ffmpeg_chain_mock(mock_ffmpeg)
        process_mock.communicate.return_value = (b"", b"")

        clip_video(Path("/tmp/in.mp4"), 500, 2000, Path("/tmp/out.mp4"))

        assert mock_ffmpeg.input.call_count == 1
        call_kwargs = mock_ffmpeg.input.call_args.kwargs
        assert call_kwargs["ss"] == pytest.approx(0.5)
        assert call_kwargs["to"] == pytest.approx(2.0)


def test_clip_video_timeout_raises():
    with patch("services.video_pipeline.ffmpeg") as mock_ffmpeg:
        process_mock = _make_ffmpeg_chain_mock(mock_ffmpeg)
        process_mock.communicate.side_effect = subprocess.TimeoutExpired("ffmpeg", 120)

        with pytest.raises(RuntimeError, match="timed out"):
            clip_video(Path("/tmp/in.mp4"), 0, 5000, Path("/tmp/out.mp4"))


# ---------------------------------------------------------------------------
# video_pipeline — extract_frames
# ---------------------------------------------------------------------------


def test_extract_frames_returns_list():
    """fps=30 + target_interval_ms=200 → frame_interval=6; only frame 0 of 3 sampled."""
    with patch("services.video_pipeline.cv2") as mock_cv2:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        # Return 30.0 for both CAP_PROP_FPS and CAP_PROP_POS_MSEC calls.
        mock_cap.get.return_value = 30.0

        frame = np.zeros((80, 100, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [
            (True, frame),
            (True, frame),
            (True, frame),
            (False, None),
        ]

        jpeg_buf = np.frombuffer(b"\xff\xd8\xff\xe0" + b"\x00" * 10, dtype=np.uint8)
        mock_cv2.imencode.return_value = (True, jpeg_buf)

        result = extract_frames(Path("/tmp/clip.mp4"), target_interval_ms=200)

        assert len(result) == 1
        ts, data = result[0]
        assert isinstance(ts, int)
        assert isinstance(data, bytes)


def test_extract_frames_caps_at_max_frames():
    """With fps=1 every frame is a sample; 1000 reads must be capped at _MAX_FRAMES=150."""
    with patch("services.video_pipeline.cv2") as mock_cv2:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        # fps=1 → frame_interval = max(1, round(1 * 200/1000)) = max(1, 0) = 1
        mock_cap.get.return_value = 1.0

        frame = np.zeros((80, 100, 3), dtype=np.uint8)
        call_count = [0]

        def _mock_read():
            call_count[0] += 1
            if call_count[0] <= 1000:
                return (True, frame)
            return (False, None)

        mock_cap.read.side_effect = _mock_read

        jpeg_buf = np.frombuffer(b"\xff\xd8\xff\xe0" + b"\x00" * 10, dtype=np.uint8)
        mock_cv2.imencode.return_value = (True, jpeg_buf)

        result = extract_frames(Path("/tmp/clip.mp4"))

        assert len(result) <= 150


# ---------------------------------------------------------------------------
# video_pipeline — assemble_annotated_clip
# ---------------------------------------------------------------------------


def test_assemble_annotated_clip_empty_raises():
    with pytest.raises(ValueError):
        assemble_annotated_clip([], Path("/tmp/out.mp4"))


def test_assemble_annotated_clip_calls_ffmpeg():
    with patch("services.video_pipeline.ffmpeg") as mock_ffmpeg:
        process_mock = _make_ffmpeg_chain_mock(mock_ffmpeg)

        frames = [(0, b"\xff\xd8\xff\xe0" + b"\x00" * 100)]
        assemble_annotated_clip(frames, Path("/tmp/out.mp4"))

        process_mock.stdin.write.assert_called_once()
        process_mock.wait.assert_called_once()


# ---------------------------------------------------------------------------
# openai_client — analyze_frames
# ---------------------------------------------------------------------------


def _patch_openai(content: str):
    """Context manager factory: patch openai.OpenAI and return a mock client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_analyze_frames_invalid_throw_type_coerced():
    """An unrecognised throw_type_hint must be silently coerced to 'unknown'."""
    with patch("services.openai_client.openai.OpenAI") as MockOpenAI:
        mock_client = _patch_openai(_VALID_CRITIQUE_JSON)
        MockOpenAI.return_value = mock_client

        analyze_frames([], throw_type_hint="invalid_value")

        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        system_content = messages[0]["content"]
        assert "unknown" in system_content


def test_analyze_frames_invalid_json_raises():
    with patch("services.openai_client.openai.OpenAI") as MockOpenAI:
        MockOpenAI.return_value = _patch_openai("not json")

        with pytest.raises(ValueError):
            analyze_frames([], throw_type_hint="unknown")


def test_analyze_frames_schema_mismatch_raises():
    """Valid JSON that does not match CritiqueResponse schema must raise ValueError."""
    with patch("services.openai_client.openai.OpenAI") as MockOpenAI:
        MockOpenAI.return_value = _patch_openai("{}")

        with pytest.raises(ValueError):
            analyze_frames([], throw_type_hint="unknown")


def test_analyze_frames_valid_returns_critique():
    with patch("services.openai_client.openai.OpenAI") as MockOpenAI:
        MockOpenAI.return_value = _patch_openai(_VALID_CRITIQUE_JSON)

        result = analyze_frames([], throw_type_hint="backhand")

        assert isinstance(result, CritiqueResponse)
        assert result.throw_type == "backhand"
