def annotate_frame(frame_bytes: bytes, label: str) -> bytes:
    """
    Overlay *label* text and pose landmarks onto *frame_bytes* (JPEG).

    Args:
        frame_bytes: Raw JPEG image data.
        label:       Text to render onto the frame (e.g., phase name + timestamp).

    Returns:
        Annotated JPEG bytes.
    """
    raise NotImplementedError
