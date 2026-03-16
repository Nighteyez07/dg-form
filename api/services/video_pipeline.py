from pathlib import Path


def clip_video(source: Path, start_ms: int, end_ms: int, output: Path) -> None:
    """Trim *source* to the [start_ms, end_ms] window and write the result to *output*."""
    raise NotImplementedError


def extract_frames(
    clip_path: Path,
    target_interval_ms: int = 200,
) -> list[tuple[int, bytes]]:
    """
    Extract representative JPEG frames from *clip_path* at approximately
    *target_interval_ms* intervals.

    Returns:
        A list of (timestamp_ms, jpeg_bytes) tuples ordered by timestamp.
    """
    raise NotImplementedError


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
    raise NotImplementedError
