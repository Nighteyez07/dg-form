import base64
import json
import logging
import os

import openai

from models.schemas import CritiqueResponse

logger = logging.getLogger(__name__)

_openai_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI()  # reads OPENAI_API_KEY from environment
    return _openai_client

_SCHEMA_DESCRIPTION = """
{
  "overall_score": "string like '7/10'",
  "summary": "2-3 sentence overview of the throw",
  "throw_type": "backhand | forehand | unknown",
  "camera_perspective": "front | back | side_facing | side_away | unknown",
  "phases": [
    {
      "name": "string (one of the standard phases)",
      "timestamp_ms": integer (pick the closest provided frame timestamp),
      "observations": ["string"],
      "recommendations": ["string"]
    }
  ],
  "key_focus": "single most impactful improvement tip"
}
"""

_SYSTEM_PROMPT_BASE = """\
You are an expert disc golf coach specialising in throw mechanics and form analysis. \
A student is submitting sequential frames captured from a video of their disc golf throw. \
Your task is to analyse their form across the following standard throw phases:

1. Grip & Setup
2. Reach-Back
3. Pull-Through
4. Release
5. Follow-Through

For each phase that is visible in the provided frames, identify what the athlete is doing \
well (observations) and provide concrete, actionable recommendations for improvement.

{throw_type_line}\
{camera_perspective_line}\
Return ONLY valid JSON that strictly matches the schema below — no markdown code fences, \
no prose, no additional keys. Any deviation will cause a processing error.

Schema:
{schema}
"""


_CAMERA_PERSPECTIVE_LINES: dict[str, str] = {
    "front": (
        "The camera is front-facing (faces the thrower's chest). "
        "Focus on: chest/hip rotation, elbow path, disc plane at release.\n"
    ),
    "back": (
        "The camera is behind the thrower. "
        "Focus on: reach-back depth, X-step footwork, follow-through direction.\n"
    ),
    "side_facing": (
        "The camera is side-on with the thrower facing toward it. "
        "Focus on: arm extension, timing of hip vs. shoulder rotation, flight angle.\n"
    ),
    "side_away": (
        "The camera is side-on with the thrower facing away. "
        "Focus on: same as side-facing with camera-left/right flipped; note limb occlusion.\n"
    ),
    "unknown": (
        "The camera angle is unclear or unknown; "
        "provide general analysis and infer what body parts are visible.\n"
    ),
}

_VALID_CAMERA_PERSPECTIVES = {"front", "back", "side_facing", "side_away", "unknown"}


def _build_system_prompt(throw_type_hint: str, camera_perspective_hint: str) -> str:
    if camera_perspective_hint not in _VALID_CAMERA_PERSPECTIVES:
        camera_perspective_hint = "unknown"

    if throw_type_hint != "unknown":
        throw_type_line = (
            f"This appears to be a {throw_type_hint} throw — focus your analysis "
            f"on mechanics specific to a {throw_type_hint} technique.\n"
        )
    else:
        throw_type_line = (
            "The throw type is unknown; identify it as part of your analysis.\n"
        )

    camera_perspective_line = _CAMERA_PERSPECTIVE_LINES[camera_perspective_hint]

    return _SYSTEM_PROMPT_BASE.format(
        throw_type_line=throw_type_line,
        camera_perspective_line=camera_perspective_line,
        schema=_SCHEMA_DESCRIPTION.strip(),
    )


_VALID_THROW_TYPES = {"backhand", "forehand", "unknown"}


def analyze_frames(
    frames: list[tuple[int, bytes]],
    throw_type_hint: str = "unknown",
    camera_perspective_hint: str = "unknown",
) -> CritiqueResponse:
    """
    Send *frames* to GPT-4o Vision and return a structured form critique.

    Args:
        frames:                   Ordered list of (timestamp_ms, jpeg_bytes) pairs.
                                  Each JPEG is base64-encoded and sent as an inline data URL.
        throw_type_hint:          Optional hint passed to the model prompt
                                  ("backhand", "forehand", or "unknown").
        camera_perspective_hint:  Optional hint describing the camera angle
                                  ("front", "back", "side_facing", "side_away", or "unknown").
                                  Directs the model to emphasise body parts visible from that angle.

    Returns:
        A validated CritiqueResponse parsed from the model's JSON output.

    Raises:
        ValueError: If the model returns unparseable JSON or output that fails
                    schema validation.
        openai.OpenAIError: Propagated as-is for the router to handle.
    """
    if throw_type_hint not in _VALID_THROW_TYPES:
        throw_type_hint = "unknown"

    if camera_perspective_hint not in _VALID_CAMERA_PERSPECTIVES:
        camera_perspective_hint = "unknown"

    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    client = _get_client()

    logger.info(
        "Sending %d frame(s) to %s (throw_type_hint=%r, camera_perspective_hint=%r)",
        len(frames),
        model,
        throw_type_hint,
        camera_perspective_hint,
    )

    system_prompt = _build_system_prompt(throw_type_hint, camera_perspective_hint)

    # Build the user message as a multi-part content list.
    perspective_note = (
        f" filmed from a {camera_perspective_hint} perspective"
        if camera_perspective_hint != "unknown"
        else ""
    )
    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Here are {len(frames)} frames from a disc golf throw{perspective_note}, "
                "ordered chronologically. Analyse the form and return the JSON critique."
            ),
        }
    ]

    for timestamp_ms, jpeg_bytes in frames:
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        user_content.append({"type": "text", "text": f"Frame at {timestamp_ms}ms:"})
        user_content.append(
            {
                "type": "image_url",
                # detail:low forces 85 tokens per image regardless of resolution,
                # keeping requests well within the gpt-4.1-mini 200k TPM limit.
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
            }
        )

    _OPENAI_TIMEOUT_S = float(os.environ.get("OPENAI_TIMEOUT_S", "30"))
    response = client.chat.completions.create(
        model=model,
        max_tokens=1500,
        temperature=0.3,
        timeout=_OPENAI_TIMEOUT_S,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    raw_content: str = response.choices[0].message.content or ""

    # Strip accidental markdown fences (```json ... ``` or ``` ... ```)
    stripped = raw_content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop opening fence line and closing fence line
        inner_lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        stripped = "\n".join(inner_lines).strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        logger.warning(
            "GPT-4o returned unparseable JSON (first 500 chars): %.500s", raw_content
        )
        raise ValueError("GPT-4o returned an invalid critique response")

    try:
        critique = CritiqueResponse.model_validate(data)
    except Exception:
        logger.warning(
            "GPT-4o response failed schema validation (first 500 chars): %.500s",
            raw_content,
        )
        raise ValueError("GPT-4o returned an invalid critique response")

    logger.info("Critique received — overall_score=%r", critique.overall_score)
    return critique
