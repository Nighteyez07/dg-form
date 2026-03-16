import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def annotate_frame(frame_bytes: bytes, label: str) -> bytes:
    """
    Overlay *label* text onto *frame_bytes* (JPEG).

    Renders the label with a black drop-shadow for legibility on any background.

    Args:
        frame_bytes: Raw JPEG image data.
        label:       Text to render (e.g., phase name + first observation).

    Returns:
        Annotated JPEG bytes.
    """
    arr = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("annotate_frame: could not decode frame bytes; buffer may be corrupt")

    height = frame.shape[0]
    x, y = 20, height - 40
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = 0.8
    thickness = 2

    # Black shadow offset by 2 px for legibility.
    cv2.putText(frame, label, (x + 2, y + 2), font, scale, (0, 0, 0), thickness, cv2.LINE_AA)
    # White text rendered on top.
    cv2.putText(frame, label, (x, y), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

    success, jpeg_buf = cv2.imencode(".jpg", frame)
    if not success:
        raise RuntimeError("Failed to re-encode annotated frame to JPEG.")
    return jpeg_buf.tobytes()
