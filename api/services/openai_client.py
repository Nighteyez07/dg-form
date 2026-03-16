from models.schemas import CritiqueResponse


def analyze_frames(
    frames: list[tuple[int, bytes]],
    throw_type_hint: str = "unknown",
) -> CritiqueResponse:
    """
    Send *frames* to GPT-4o Vision and return a structured form critique.

    Args:
        frames:           Ordered list of (timestamp_ms, jpeg_bytes) pairs.
        throw_type_hint:  Optional hint passed to the model prompt
                          ("backhand", "forehand", or "unknown").

    Returns:
        A validated CritiqueResponse parsed from the model's JSON output.
    """
    raise NotImplementedError
