import base64
import json
import logging
import os

import openai

from models.schemas import CritiqueResponse

logger = logging.getLogger(__name__)

_SCHEMA_DESCRIPTION = """
{
  "overall_score": "string like '7/10'",
  "summary": "2-3 sentence overview of the throw",
  "throw_type": "backhand | forehand | unknown",
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

Return ONLY valid JSON that strictly matches the schema below — no markdown code fences, \
no prose, no additional keys. Any deviation will cause a processing error.

Schema:
{schema}
"""


def _build_system_prompt(throw_type_hint: str) -> str:
    if throw_type_hint != "unknown":
        throw_type_line = (
            f"This appears to be a {throw_type_hint} throw — focus your analysis "
            f"on mechanics specific to a {throw_type_hint} technique.\n"
        )
    else:
        throw_type_line = (
            "The throw type is unknown; identify it as part of your analysis.\n"
        )
    return _SYSTEM_PROMPT_BASE.format(
        throw_type_line=throw_type_line,
        schema=_SCHEMA_DESCRIPTION.strip(),
    )


_VALID_THROW_TYPES = {"backhand", "forehand", "unknown"}


def analyze_frames(
    frames: list[tuple[int, bytes]],
    throw_type_hint: str = "unknown",
) -> CritiqueResponse:
    """
    Send *frames* to GPT-4o Vision and return a structured form critique.

    Args:
        frames:           Ordered list of (timestamp_ms, jpeg_bytes) pairs.
                          Each JPEG is base64-encoded and sent as an inline data URL.
        throw_type_hint:  Optional hint passed to the model prompt
                          ("backhand", "forehand", or "unknown").

    Returns:
        A validated CritiqueResponse parsed from the model's JSON output.

    Raises:
        ValueError: If the model returns unparseable JSON or output that fails
                    schema validation.
        openai.OpenAIError: Propagated as-is for the router to handle.
    """
    if throw_type_hint not in _VALID_THROW_TYPES:
        throw_type_hint = "unknown"

    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    client = openai.OpenAI()  # reads OPENAI_API_KEY from environment

    logger.info(
        "Sending %d frame(s) to %s (throw_type_hint=%r)",
        len(frames),
        model,
        throw_type_hint,
    )

    system_prompt = _build_system_prompt(throw_type_hint)

    # Build the user message as a multi-part content list.
    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Here are {len(frames)} frames from a disc golf throw, ordered "
                "chronologically. Analyse the form and return the JSON critique."
            ),
        }
    ]

    for timestamp_ms, jpeg_bytes in frames:
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        user_content.append({"type": "text", "text": f"Frame at {timestamp_ms}ms:"})
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
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
