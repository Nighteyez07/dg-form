import logging
import subprocess
from pathlib import Path

import cv2
import ffmpeg

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_S = 120  # max seconds any ffmpeg process may run
_MAX_FRAMES = 12         # hard cap: 8-12 frames covers all throw phases; more = token waste


def clip_video(source: Path, start_ms: int, end_ms: int, output: Path) -> None:
    """Trim *source* to the [start_ms, end_ms] window and write the result to *output*."""
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    logger.info("Clipping %s [%.3fs → %.3fs] to %s", source, start_s, end_s, output)
    process = (
        ffmpeg
        .input(str(source), ss=start_s, to=end_s)
        .output(str(output), c="copy")
        .overwrite_output()
        .run_async(quiet=True)
    )
    try:
        process.communicate(timeout=_FFMPEG_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError(f"ffmpeg clip_video timed out after {_FFMPEG_TIMEOUT_S}s")
    logger.info("Clip written to %s", output)


def extract_frames(
    clip_path: Path,
    target_interval_ms: int = 500,
) -> list[tuple[int, bytes]]:
    """
    Extract representative JPEG frames from *clip_path* at approximately
    *target_interval_ms* intervals.

    Returns:
        A list of (timestamp_ms, jpeg_bytes) tuples ordered by timestamp.
    """
    cap = cv2.VideoCapture(str(clip_path))
    frames: list[tuple[int, bytes]] = []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_interval = max(1, int(round(fps * target_interval_ms / 1000.0)))
        frame_index = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_index % frame_interval == 0:
                timestamp_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
                success, jpeg_buf = cv2.imencode(".jpg", frame)
                if success:
                    frames.append((timestamp_ms, jpeg_buf.tobytes()))
                if len(frames) >= _MAX_FRAMES:
                    logger.warning(
                        "extract_frames: hit _MAX_FRAMES=%d cap; stopping early",
                        _MAX_FRAMES,
                    )
                    break
            frame_index += 1
    finally:
        cap.release()
    logger.info("Extracted %d frames from %s", len(frames), clip_path)
    return frames


def assemble_annotated_clip(
    frames: list[tuple[int, bytes]],
    output: Path,
) -> None:
    """
    Re-encode *frames* (annotated JPEG bytes with timestamps) into an MP4 at *output*.

    Args:
        frames: Ordered list of (timestamp_ms, jpeg_bytes) to encode.
        output: Destination path for the finished MP4.
    """
    if not frames:
        raise ValueError("Cannot assemble clip from an empty frames list.")

    if len(frames) == 1:
        fps = 10.0
    else:
        duration_ms = frames[-1][0] - frames[0][0]
        fps = (len(frames) - 1) / (duration_ms / 1000.0) if duration_ms > 0 else 10.0

    process = (
        ffmpeg
        .input("pipe:", format="image2pipe", framerate=fps)
        .output(str(output), vcodec="libx264", pix_fmt="yuv420p")
        .overwrite_output()
        .run_async(pipe_stdin=True, quiet=True)
    )
    try:
        for _, jpeg_bytes in frames:
            process.stdin.write(jpeg_bytes)
        process.stdin.close()
        process.wait(timeout=_FFMPEG_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError(
            f"ffmpeg assemble_annotated_clip timed out after {_FFMPEG_TIMEOUT_S}s"
        )
    except Exception:
        process.kill()
        raise
    logger.info(
        "Assembled annotated clip (%d frames, %.1f fps) → %s", len(frames), fps, output
    )
