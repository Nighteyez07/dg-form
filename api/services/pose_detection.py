from pathlib import Path


def detect_throw_segment(video_path: Path) -> dict:
    """
    Analyse *video_path* with MediaPipe Pose and identify the disc-golf throw segment.

    Returns a dict with keys:
        start_ms       (int)  – detected throw start in milliseconds
        end_ms         (int)  – detected throw end in milliseconds
        duration_ms    (int)  – total video duration in milliseconds
        low_confidence (bool) – True when the detection heuristic is uncertain
    """
    raise NotImplementedError
