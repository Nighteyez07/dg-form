import logging
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


def detect_throw_segment(video_path: Path) -> dict:
    """
    Analyse *video_path* with MediaPipe Pose and identify the disc-golf throw segment.

    Returns a dict with keys:
        start_ms       (int)  – detected throw start in milliseconds
        end_ms         (int)  – detected throw end in milliseconds
        duration_ms    (int)  – total video duration in milliseconds
        low_confidence (bool) – True when the detection heuristic is uncertain
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration_ms = int((frame_count / fps) * 1000)
    finally:
        cap.release()

    logger.info(
        "detect_throw_segment: duration=%dms (stub — returning full clip, low_confidence=True)",
        duration_ms,
    )
    return {
        "start_ms": 0,
        "end_ms": duration_ms,
        "duration_ms": duration_ms,
        "low_confidence": True,
    }
