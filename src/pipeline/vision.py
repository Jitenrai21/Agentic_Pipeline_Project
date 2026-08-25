from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from groq import Groq

from .config import get_groq_api_key

client = None


def _get_client() -> Groq:
    global client
    if client is None:
        client = Groq(api_key=get_groq_api_key())
    return client


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from LLM response, handling any preamble or markdown."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find the first { and last } to extract JSON block
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Try extracting from ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", raw)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response:\n{raw[:500]}")


VISION_SYSTEM_PROMPT = """Extract technical specifications from solar inverter datasheet images.
Output ONLY a JSON object. No thinking, no explanation, no markdown."""

VISION_USER_PROMPT = """Look at this solar inverter datasheet image. Extract ALL visible specifications.

Return ONLY this JSON structure (no other text):
{"page_text": "all visible text on page", "tables": [{"headers": ["column names"], "rows": [["cell values"]]}], "key_values": {"specification_name": {"value": "number or text", "unit": "unit if applicable"}}}

Important:
- Extract the text exactly as it appears
- Include ALL numbers and values you can read
- For tables, preserve the row/column structure
- For key_values, use descriptive names like "rated_power", "max_efficiency", "weight"
- If you cannot read something clearly, write "unclear" as the value
- Output ONLY the JSON, nothing else"""


def image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_with_vision(image_path: Path) -> dict:
    """
    Send an image to Groq Qwen 3.6 27B and extract structured data.
    """
    groq_client = _get_client()
    b64_image = image_to_base64(image_path)

    completion = groq_client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}"
                        },
                    },
                ],
            },
        ],
        temperature=0.1,
        max_completion_tokens=8192,
    )

    raw = completion.choices[0].message.content
    return _parse_json_response(raw)


def extract_text_with_llm(text: str) -> dict:
    """
    Send extracted text to LLM for structured field extraction.
    Used when pdfplumber output is messy but readable.
    """
    groq_client = _get_client()

    completion = groq_client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Extract structured data from this solar inverter datasheet text.

TEXT:
{text}

Return this exact JSON structure:
{{"page_text": "cleaned full text", "tables": [{{"headers": ["col1"], "rows": [["val1"]]}}], "key_values": {{"field_name": {{"value": "val", "unit": "unit"}}}}}}""",
            },
        ],
        temperature=0.1,
        max_completion_tokens=8192,
    )

    raw = completion.choices[0].message.content
    return _parse_json_response(raw)
