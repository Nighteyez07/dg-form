"""
Integration tests for POST /api/analyze and GET /api/clip/{clip_id}.

Strategy
--------
- `_upload_registry` is imported directly from `routers.upload` and populated
  in the `registry_entry` fixture so tests control exactly what is "in-flight".
- All four service functions called by analyze_video are patched at the
  services module level so the stubs' NotImplementedError is never reached.
- The `registry_entry` fixture removes its own entry on teardown; the route
  itself also pops the entry in its finally block, so both sides are safe to
  call `.pop(…, None)`.
"""

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from routers.upload import _upload_registry
from models.schemas import CritiqueResponse, ThrowPhase

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TMP_DIR = Path("/tmp/dg-form")

# A fully-valid CritiqueResponse returned by the mocked openai_client.
_VALID_CRITIQUE = CritiqueResponse(
    overall_score="8/10",
    summary="Clean mechanics with strong hip rotation.",
    throw_type="backhand",
    phases=[
        ThrowPhase(
            name="Release",
            timestamp_ms=2000,
            observations=["Good snap at release"],
            recommendations=["Extend follow-through further"],
        )
    ],
    key_focus="Follow through",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry_entry(tmp_path: Path):
    """Insert a fake upload entry and yield (upload_id, file_path).

    Uses pytest's tmp_path so the file lives on a real filesystem path that
    is automatically cleaned up by pytest after the test session.  The route's
    finally block will unlink the file; missing_ok=True makes both sides safe.
    """
    upload_id = str(uuid.uuid4())
    video_file = tmp_path / "test_upload.mp4"
    # Write a tiny fake payload — content doesn't matter since service calls are mocked.
    video_file.write_bytes(b"\x00\x00\x00\x0cftyp" + b"\x00" * 188)

    _upload_registry[upload_id] = (video_file, datetime.utcnow())

    yield upload_id, video_file

    # Teardown: guard against the route having already removed the entry/file.
    _upload_registry.pop(upload_id, None)
    video_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# POST /api/analyze — validation / not-found paths
# ---------------------------------------------------------------------------

async def test_analyze_invalid_uuid(async_client) -> None:
    response = await async_client.post(
        "/analyze",
        json={"upload_id": "not-a-uuid", "trim": {"start_ms": 0, "end_ms": 2000}},
    )
    assert response.status_code == 404


async def test_analyze_upload_not_found(async_client) -> None:
    valid_uuid = str(uuid.uuid4())  # real UUID, but not in the registry
    response = await async_client.post(
        "/analyze",
        json={"upload_id": valid_uuid, "trim": {"start_ms": 0, "end_ms": 2000}},
    )
    assert response.status_code == 404


async def test_analyze_invalid_trim_range(async_client, registry_entry) -> None:
    upload_id, _ = registry_entry
    # end_ms < start_ms — TrimRange model_validator must reject this with 422.
    response = await async_client.post(
        "/analyze",
        json={"upload_id": upload_id, "trim": {"start_ms": 5000, "end_ms": 1000}},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/analyze — happy path
# ---------------------------------------------------------------------------

async def test_analyze_services_called(async_client, registry_entry) -> None:
    upload_id, _ = registry_entry

    with (
        patch("services.video_pipeline.clip_video"),
        patch("services.video_pipeline.extract_frames", return_value=[]),
        patch("services.video_pipeline.assemble_annotated_clip"),
        patch("services.openai_client.analyze_frames", return_value=_VALID_CRITIQUE),
    ):
        response = await async_client.post(
            "/analyze",
            json={"upload_id": upload_id, "trim": {"start_ms": 0, "end_ms": 2000}},
        )

    assert response.status_code == 200
    data = response.json()
    assert "clip_id" in data
    assert data["critique"]["throw_type"] == "backhand"


async def test_analyze_cleans_up_upload(async_client, registry_entry) -> None:
    upload_id, upload_path = registry_entry

    with (
        patch("services.video_pipeline.clip_video"),
        patch("services.video_pipeline.extract_frames", return_value=[]),
        patch("services.video_pipeline.assemble_annotated_clip"),
        patch("services.openai_client.analyze_frames", return_value=_VALID_CRITIQUE),
    ):
        response = await async_client.post(
            "/analyze",
            json={"upload_id": upload_id, "trim": {"start_ms": 0, "end_ms": 2000}},
        )

    assert response.status_code == 200
    # The route's finally block must have deleted the source upload file.
    assert not upload_path.exists()


# ---------------------------------------------------------------------------
# GET /api/clip/{clip_id}
# ---------------------------------------------------------------------------

async def test_get_clip_invalid_uuid(async_client) -> None:
    response = await async_client.get("/clip/not-a-uuid")
    assert response.status_code == 404


async def test_get_clip_not_found(async_client) -> None:
    valid_uuid = str(uuid.uuid4())
    response = await async_client.get(f"/clip/{valid_uuid}")
    assert response.status_code == 404


async def test_get_clip_streams_annotated(async_client) -> None:
    clip_id = str(uuid.uuid4())
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    annotated_path = _TMP_DIR / f"{clip_id}_annotated.mp4"
    # Write a plausible MP4-like payload so FileResponse has something to stream.
    annotated_path.write_bytes(b"\x00\x00\x00\x1cftyp" + b"\x00" * 100)

    try:
        response = await async_client.get(f"/clip/{clip_id}")
        assert response.status_code == 200
        assert "video/mp4" in response.headers["content-type"]
    finally:
        # Route adds a background task that deletes the file; missing_ok is safe.
        annotated_path.unlink(missing_ok=True)
