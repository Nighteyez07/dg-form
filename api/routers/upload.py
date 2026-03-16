import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile

from models.schemas import SuggestedTrim, UploadResponse
from services import pose_detection

logger = logging.getLogger(__name__)

router = APIRouter()

_TMP_DIR = Path("/tmp/dg-form")
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
_CHUNK_SIZE = 1024 * 1024  # 1 MB

_ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "video/mp4",
    "video/quicktime",
    "video/3gpp",
    "video/webm",
})

_MIME_TO_EXT: dict[str, str] = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/3gpp": ".3gp",
    "video/webm": ".webm",
}

_MAGIC_BYTES: dict[str, list[bytes]] = {
    "video/mp4":       [b"ftyp"],              # at offset 4, ISO base media
    "video/quicktime": [b"ftyp"],              # at offset 4, ISO base media
    "video/3gpp":      [b"ftyp"],              # at offset 4, ISO base media
    "video/webm":      [b"\x1a\x45\xdf\xa3"],  # at offset 0, EBML header
}

# In-memory registry: upload_id -> (temp file Path, registered_at).
# MVP caveat: lost on process restart; replace with a persistent store for production.
_upload_registry: dict[str, tuple[Path, datetime]] = {}

_UPLOAD_TTL_SECONDS: int = 900  # 15 minutes

_eviction_task: asyncio.Task | None = None


async def _eviction_loop() -> None:
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        stale = [
            uid
            for uid, (path, registered_at) in list(_upload_registry.items())
            if (now - registered_at).total_seconds() > _UPLOAD_TTL_SECONDS
        ]
        for uid in stale:
            entry = _upload_registry.pop(uid, None)
            if entry:
                path, _ = entry
                path.unlink(missing_ok=True)
                logger.info("Evicted stale upload %s \u2192 %s", uid, path)


async def start_eviction_task() -> None:
    global _eviction_task
    _eviction_task = asyncio.create_task(_eviction_loop())
    logger.info("Upload eviction task started (TTL=%ds)", _UPLOAD_TTL_SECONDS)


@router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_video(video: UploadFile) -> UploadResponse:
    # --- MIME validation ---
    content_type = (video.content_type or "").lower()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported media type. Accepted: video/mp4, video/quicktime, video/3gpp, video/webm.",
        )

    upload_id = str(uuid.uuid4())
    ext = _MIME_TO_EXT[content_type]
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = _TMP_DIR / f"{upload_id}{ext}"

    # Track whether the full handler succeeded so the finally block knows
    # whether to clean up the temp file or leave it for /analyze.
    success = False
    try:
        total_bytes = 0
        async with aiofiles.open(temp_path, "wb") as fh:
            while True:
                chunk = await video.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Upload exceeds the 200 MB size limit.",
                    )
                await fh.write(chunk)
        logger.info("Saved upload %s (%d bytes) → %s", upload_id, total_bytes, temp_path)

        # --- Magic-byte validation ---
        async with aiofiles.open(temp_path, "rb") as fh:
            header = await fh.read(16)
        sigs = _MAGIC_BYTES[content_type]
        offset = 0 if content_type == "video/webm" else 4
        valid = any(
            len(header) >= offset + len(sig) and header[offset : offset + len(sig)] == sig
            for sig in sigs
        )
        if not valid:
            raise HTTPException(
                status_code=415,
                detail="File content does not match the declared media type.",
            )

        result: dict = await asyncio.to_thread(
            pose_detection.detect_throw_segment, temp_path
        )

        _upload_registry[upload_id] = (temp_path, datetime.utcnow())
        success = True

        return UploadResponse(
            upload_id=upload_id,
            duration_ms=result["duration_ms"],
            suggested_trim=SuggestedTrim(
                start_ms=result["start_ms"],
                end_ms=result["end_ms"],
            ),
            low_confidence=result["low_confidence"],
        )

    finally:
        # On failure only: remove the temp file so no orphaned data is left on disk.
        # On success: temp file is intentionally kept alive for the /analyze step.
        if not success:
            temp_path.unlink(missing_ok=True)
            logger.info("Cleaned up failed upload temp file %s", temp_path)
