import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from models.schemas import AnalyzeRequest, AnalyzeResponse
from routers.upload import _upload_registry
from services import openai_client, video_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

_TMP_DIR = Path("/tmp/dg-form")


def _delete_file(path: Path) -> None:
    """Remove *path* silently — used as a cleanup BackgroundTask."""
    path.unlink(missing_ok=True)
    logger.info("Deleted file %s", path)


@router.post("/analyze", response_model=AnalyzeResponse, status_code=200)
async def analyze_video(request: AnalyzeRequest) -> AnalyzeResponse:
    # Validate upload_id is a real v4 UUID to prevent any path-traversal attempt.
    try:
        uuid.UUID(request.upload_id, version=4)
    except ValueError:
        raise HTTPException(status_code=404, detail="Upload not found.")

    entry = _upload_registry.get(request.upload_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    upload_path, _ = entry

    clip_id = str(uuid.uuid4())
    clip_path = _TMP_DIR / f"{clip_id}.mp4"
    annotated_clip_path = _TMP_DIR / f"{clip_id}_annotated.mp4"

    error_occurred = False
    try:
        # --- Clip source video to the confirmed trim range (stub) ---
        await asyncio.to_thread(
            video_pipeline.clip_video,
            upload_path,
            request.trim.start_ms,
            request.trim.end_ms,
            clip_path,
        )

        # --- Extract frames for AI analysis (stub) ---
        frames: list[tuple[int, bytes]] = await asyncio.to_thread(
            video_pipeline.extract_frames, clip_path
        )

        # --- Build annotated clip (stub) ---
        await asyncio.to_thread(
            video_pipeline.assemble_annotated_clip, frames, annotated_clip_path
        )

        # --- AI critique (stub) ---
        critique = await asyncio.to_thread(openai_client.analyze_frames, frames)

        logger.info(
            "Analysis complete: upload=%s clip=%s", request.upload_id, clip_id
        )
        return AnalyzeResponse(clip_id=clip_id, critique=critique)

    except Exception:
        error_occurred = True
        raise

    finally:
        # Always remove the source upload — it is no longer needed after analysis.
        upload_path.unlink(missing_ok=True)
        _upload_registry.pop(request.upload_id, None)
        logger.info("Removed source upload %s", upload_path)

        # raw clip is an intermediate file — always remove it.
        clip_path.unlink(missing_ok=True)
        # On failure: also clean up the partially-written annotated clip.
        # On success: annotated_clip_path is kept alive for GET /clip/{clip_id};
        # the streaming endpoint deletes it via BackgroundTask afterward.
        if error_occurred:
            annotated_clip_path.unlink(missing_ok=True)
            logger.info("Cleaned up partial clips after error: %s, %s", clip_path, annotated_clip_path)


@router.get("/clip/{clip_id}", response_class=FileResponse)
async def get_clip(clip_id: str, background_tasks: BackgroundTasks) -> FileResponse:
    # Validate clip_id is a real v4 UUID to prevent path-traversal.
    try:
        uuid.UUID(clip_id, version=4)
    except ValueError:
        raise HTTPException(status_code=404, detail="Clip not found.")

    clip_path = _TMP_DIR / f"{clip_id}_annotated.mp4"
    if not clip_path.is_file():
        raise HTTPException(status_code=404, detail="Clip not found.")

    # Delete the file from disk after the response has been fully streamed.
    background_tasks.add_task(_delete_file, clip_path)
    logger.info("Streaming clip %s", clip_id)
    return FileResponse(clip_path, media_type="video/mp4", filename=f"{clip_id}.mp4")
