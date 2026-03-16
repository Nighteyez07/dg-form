import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from models.schemas import AnalyzeRequest, AnalyzeResponse, CritiqueResponse
from routers.upload import _upload_registry
from services import annotation, openai_client, video_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

_TMP_DIR = Path("/tmp/dg-form")
_ANALYZE_SEMAPHORE = asyncio.Semaphore(4)  # cap concurrent expensive OpenAI+ffmpeg calls


def _delete_file(path: Path) -> None:
    """Remove *path* silently — used as a cleanup BackgroundTask."""
    path.unlink(missing_ok=True)
    logger.info("Deleted file %s", path)


def _annotate_frames_with_critique(
    frames: list[tuple[int, bytes]],
    critique: CritiqueResponse,
) -> list[tuple[int, bytes]]:
    """Return a new frames list where each critique phase annotates its nearest frame."""
    if not frames:
        return frames

    frame_timestamps = [ts for ts, _ in frames]
    index_to_label: dict[int, str] = {}

    for phase in critique.phases:
        closest_idx = min(
            range(len(frame_timestamps)),
            key=lambda i: abs(frame_timestamps[i] - phase.timestamp_ms),
        )
        _MAX_LABEL = 80
        label = (
            f"{phase.name}: {phase.observations[0]}"
            if phase.observations
            else phase.name
        )
        index_to_label[closest_idx] = label[:_MAX_LABEL]

    result: list[tuple[int, bytes]] = []
    for i, (ts, frame_bytes) in enumerate(frames):
        if i in index_to_label:
            frame_bytes = annotation.annotate_frame(frame_bytes, index_to_label[i])
        result.append((ts, frame_bytes))

    return result


@router.post("/analyze", response_model=AnalyzeResponse, status_code=200)
async def analyze_video(request: AnalyzeRequest) -> AnalyzeResponse:
    # Validate upload_id is a real v4 UUID to prevent any path-traversal attempt.
    try:
        uuid.UUID(request.upload_id, version=4)
    except ValueError:
        raise HTTPException(status_code=404, detail="Upload not found.")

    entry = _upload_registry.pop(request.upload_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    upload_path, _ = entry

    clip_id = str(uuid.uuid4())
    clip_path = _TMP_DIR / f"{clip_id}.mp4"
    annotated_clip_path = _TMP_DIR / f"{clip_id}_annotated.mp4"

    error_occurred = False
    async with _ANALYZE_SEMAPHORE:
        try:
            # --- Clip source video to the confirmed trim range ---
            await asyncio.to_thread(
                video_pipeline.clip_video,
                upload_path,
                request.trim.start_ms,
                request.trim.end_ms,
                clip_path,
            )

            # --- Extract frames for AI analysis ---
            raw_frames: list[tuple[int, bytes]] = await asyncio.to_thread(
                video_pipeline.extract_frames, clip_path
            )

            # --- AI critique ---
            critique = await asyncio.to_thread(openai_client.analyze_frames, raw_frames)

            # --- Annotate frames with critique phases ---
            annotated_frames: list[tuple[int, bytes]] = await asyncio.to_thread(
                _annotate_frames_with_critique, raw_frames, critique
            )

            # --- Build annotated clip ---
            await asyncio.to_thread(
                video_pipeline.assemble_annotated_clip, annotated_frames, annotated_clip_path
            )

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
        clip_id = str(uuid.UUID(clip_id, version=4))  # normalize to canonical lowercase
    except ValueError:
        raise HTTPException(status_code=404, detail="Clip not found.")

    clip_path = _TMP_DIR / f"{clip_id}_annotated.mp4"
    if not clip_path.is_file():
        raise HTTPException(status_code=404, detail="Clip not found.")

    # Delete the file from disk after the response has been fully streamed.
    background_tasks.add_task(_delete_file, clip_path)
    logger.info("Streaming clip %s", clip_id)
    return FileResponse(clip_path, media_type="video/mp4", filename=f"{clip_id}.mp4")
