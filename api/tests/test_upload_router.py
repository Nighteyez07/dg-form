"""
Integration tests for POST /api/upload.

Strategy
--------
- The ASGI app is exercised end-to-end via httpx AsyncASGITransport.
- `pose_detection.detect_throw_segment` is patched at the services module level
  so the route's `asyncio.to_thread(pose_detection.detect_throw_segment, …)`
  call resolves without touching the real (stub) implementation.
- After every test the upload registry and any temp files created during the
  test are cleaned up by the `_cleanup_registry` autouse fixture so no state
  leaks between tests.
"""

import pytest
from unittest.mock import patch

from routers.upload import _upload_registry

# ---------------------------------------------------------------------------
# Test payloads
# ---------------------------------------------------------------------------

# Minimal valid MP4: bytes 0-3 are size, bytes 4-7 are "ftyp" (ISO base media).
_VALID_MP4 = b"\x00\x00\x00\x0cftyp" + b"\x00" * 188  # 196 bytes

# Minimal valid WebM: EBML header magic at offset 0.
_VALID_WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 192  # 196 bytes

# A detected-segment result that pose_detection stubs should return.
_DETECT_RESULT = {
    "start_ms": 1000,
    "end_ms": 3000,
    "duration_ms": 5000,
    "low_confidence": False,
    "detected_throw_type": "backhand",
    "throw_type_confidence": 0.85,
}

_DETECT_RESULT_LOW_CONF = {**_DETECT_RESULT, "low_confidence": True}

_DETECT_RESULT_UNKNOWN_THROW = {
    **_DETECT_RESULT,
    "detected_throw_type": "unknown",
    "throw_type_confidence": 0.45,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _cleanup_registry():
    """Remove temp files and clear registry entries after every test."""
    yield
    for _uid, (path, _registered_at) in list(_upload_registry.items()):
        path.unlink(missing_ok=True)
    _upload_registry.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_upload_valid_mp4(async_client) -> None:
    with patch(
        "services.pose_detection.detect_throw_segment",
        return_value=_DETECT_RESULT,
    ):
        response = await async_client.post(
            "/upload",
            files={"video": ("throw.mp4", _VALID_MP4, "video/mp4")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "upload_id" in data
    assert data["duration_ms"] == 5000
    assert data["suggested_trim"]["start_ms"] == 1000
    assert data["suggested_trim"]["end_ms"] == 3000
    assert data["low_confidence"] is False
    assert data["detected_throw_type"] == "backhand"
    assert data["throw_type_confidence"] == pytest.approx(0.85)


async def test_upload_invalid_mime(async_client) -> None:
    response = await async_client.post(
        "/upload",
        files={"video": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 415
    detail = response.json().get("detail", "")
    # Error message must never reflect the user-supplied content-type back.
    assert "text/plain" not in detail


async def test_upload_too_large(async_client) -> None:
    # Patch the limit to 100 bytes so we don't need to allocate 200 MB in memory.
    # Any valid-MIME payload larger than 100 bytes will trigger the 413 before
    # reaching the magic-byte check.
    payload = b"\x00" * 200  # 200 bytes > patched limit of 100

    with patch("routers.upload._MAX_UPLOAD_BYTES", 100):
        response = await async_client.post(
            "/upload",
            files={"video": ("big.mp4", payload, "video/mp4")},
        )

    assert response.status_code == 413


async def test_upload_magic_byte_mismatch(async_client) -> None:
    # File claims to be video/mp4 but contains no "ftyp" at offset 4.
    bad_content = b"\x00" * 200

    response = await async_client.post(
        "/upload",
        files={"video": ("fake.mp4", bad_content, "video/mp4")},
    )

    assert response.status_code == 415


async def test_upload_valid_webm(async_client) -> None:
    with patch(
        "services.pose_detection.detect_throw_segment",
        return_value=_DETECT_RESULT,
    ):
        response = await async_client.post(
            "/upload",
            files={"video": ("throw.webm", _VALID_WEBM, "video/webm")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "upload_id" in data


async def test_upload_low_confidence(async_client) -> None:
    with patch(
        "services.pose_detection.detect_throw_segment",
        return_value=_DETECT_RESULT_LOW_CONF,
    ):
        response = await async_client.post(
            "/upload",
            files={"video": ("throw.mp4", _VALID_MP4, "video/mp4")},
        )

    assert response.status_code == 200
    assert response.json()["low_confidence"] is True


async def test_upload_returns_detected_throw_type(async_client) -> None:
    with patch(
        "services.pose_detection.detect_throw_segment",
        return_value=_DETECT_RESULT,
    ):
        response = await async_client.post(
            "/upload",
            files={"video": ("throw.mp4", _VALID_MP4, "video/mp4")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["detected_throw_type"] == "backhand"
    assert data["throw_type_confidence"] == pytest.approx(0.85)


async def test_upload_unknown_throw_type_when_low_throw_type_confidence(async_client) -> None:
    with patch(
        "services.pose_detection.detect_throw_segment",
        return_value=_DETECT_RESULT_UNKNOWN_THROW,
    ):
        response = await async_client.post(
            "/upload",
            files={"video": ("throw.mp4", _VALID_MP4, "video/mp4")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["detected_throw_type"] == "unknown"
    assert data["throw_type_confidence"] == pytest.approx(0.45)
