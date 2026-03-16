import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from models.schemas import AnalyzeRequest, CritiqueResponse
from routers.upload import _upload_registry
from services import annotation, openai_client, video_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

_TMP_DIR = Path("/tmp/dg-form")
_ANALYZE_SEMAPHORE = asyncio.Semaphore(4)  # cap concurrent expensive OpenAI+ffmpeg calls

# (stage_key, human-readable message, step_number)
_STAGES = [
    ("clipping",   "Trimming video to selected range…",  1),
    ("extracting", "Extracting key frames…",             2),
    ("analyzing",  "Sending frames to AI coach…",        3),
    ("annotating", "Annotating frames with critique…",   4),
    ("assembling", "Building annotated clip…",           5),
]
_TOTAL_STEPS = len(_STAGES)


def _sse_event(event_type: str, data: dict) -> str:  # type: ignore[type-arg]
    if "\n" in event_type or "\r" in event_type:
        raise ValueError(f"Invalid SSE event type: {event_type!r}")
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


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


@router.post("/analyze")
async def analyze_video(request: AnalyzeRequest) -> StreamingResponse:
    # Validate upload_id is a real v4 UUID to prevent any path-traversal attempt.
    # Done BEFORE returning a StreamingResponse so 404 arrives as a proper HTTP error.
    try:
        uuid.UUID(request.upload_id, version=4)
    except ValueError:
        raise HTTPException(status_code=404, detail="Upload not found.")

    entry = _upload_registry.pop(request.upload_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    upload_path, _ = entry

    async def _stream() -> AsyncGenerator[str, None]:
        clip_id = str(uuid.uuid4())
        clip_path = _TMP_DIR / f"{clip_id}.mp4"
        annotated_clip_path = _TMP_DIR / f"{clip_id}_annotated.mp4"
        complete_sent = False

        yield _sse_event("queued", {"message": "Waiting for an analysis slot…"})
        async with _ANALYZE_SEMAPHORE:
            try:
                # Stage 1 — clip
                stage, message, step = _STAGES[0]
                yield _sse_event("progress", {"stage": stage, "message": message, "step": step, "total_steps": _TOTAL_STEPS})
                await asyncio.to_thread(
                    video_pipeline.clip_video,
                    upload_path,
                    request.trim.start_ms,
                    request.trim.end_ms,
                    clip_path,
                )

                # Stage 2 — extract frames
                stage, message, step = _STAGES[1]
                yield _sse_event("progress", {"stage": stage, "message": message, "step": step, "total_steps": _TOTAL_STEPS})
                raw_frames: list[tuple[int, bytes]] = await asyncio.to_thread(
                    video_pipeline.extract_frames, clip_path
                )

                # Stage 3 — AI critique
                stage, message, step = _STAGES[2]
                yield _sse_event("progress", {"stage": stage, "message": message, "step": step, "total_steps": _TOTAL_STEPS})
                critique: CritiqueResponse = await asyncio.to_thread(
                    openai_client.analyze_frames,
                    raw_frames,
                    request.throw_type.value,
                    request.camera_perspective.value,
                )

                # Stage 4 — annotate
                stage, message, step = _STAGES[3]
                yield _sse_event("progress", {"stage": stage, "message": message, "step": step, "total_steps": _TOTAL_STEPS})
                annotated_frames: list[tuple[int, bytes]] = await asyncio.to_thread(
                    _annotate_frames_with_critique, raw_frames, critique
                )
                del raw_frames  # free frame buffer before stage 5 assembly

                # Stage 5 — assemble
                stage, message, step = _STAGES[4]
                yield _sse_event("progress", {"stage": stage, "message": message, "step": step, "total_steps": _TOTAL_STEPS})
                await asyncio.to_thread(
                    video_pipeline.assemble_annotated_clip, annotated_frames, annotated_clip_path
                )

                logger.info(
                    "Analysis complete: upload=%s clip=%s", request.upload_id, clip_id
                )
                yield _sse_event(
                    "complete",
                    {"clip_id": clip_id, "critique": critique.model_dump()},
                )
                complete_sent = True

            except Exception:
                logger.exception("Analysis failed for upload=%s", request.upload_id)
                yield _sse_event("error", {"message": "Analysis failed. Please try again."})

            finally:
                # Always remove the source upload — it is no longer needed after analysis.
                upload_path.unlink(missing_ok=True)
                logger.info("Removed source upload %s", upload_path)

                # Raw clip is an intermediate file — always remove it.
                clip_path.unlink(missing_ok=True)
                # Delete the annotated clip if the complete event was never delivered
                # (error, cancellation, or client disconnect before ACK). On success
                # the file is kept alive for GET /clip/{clip_id} which deletes it via
                # BackgroundTask after the stream is fully consumed.
                if not complete_sent:
                    annotated_clip_path.unlink(missing_ok=True)
                    logger.info(
                        "Cleaned up unreachable clip after non-complete stream: %s",
                        annotated_clip_path,
                    )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
