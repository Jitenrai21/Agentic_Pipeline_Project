from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import get_openrouter_api_key, OPENROUTER_MODEL, OPENROUTER_BASE_URL


def _clean_reasoning_output(text: str) -> str:
    """Remove reasoning blocks from LLM output."""
    # Remove complete thinking tags
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    # Handle incomplete/truncated thinking tags
    match = re.search(r"<think>", text)
    if match:
        before = text[:match.start()]
        after = text[match.end():]
        json_start = after.find("{")
        if json_start != -1:
            text = before + after[json_start:]
        else:
            text = before

    # Handle models that output thinking without tags
    # Look for JSON block - if there's text before it that looks like reasoning, strip it
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        json_candidate = json_match.group(0)
        # Validate it's actually JSON
        try:
            json.loads(json_candidate)
            # If valid JSON found, check if there's significant text before it
            before_json = text[:json_match.start()].strip()
            if before_json and len(before_json) > 50:
                # There's reasoning text before JSON - use just the JSON
                return json_candidate
            return text.strip()
        except json.JSONDecodeError:
            pass

    return text.strip()


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from LLM response."""
    cleaned = _clean_reasoning_output(raw)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass

    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", cleaned)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response:\n{cleaned[:500]}")


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> dict:
    """
    Call OpenRouter LLM with a prompt and return parsed JSON response.
    """
    api_key = get_openrouter_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        if not resp.is_success:
            error_detail = resp.text[:500]
            raise RuntimeError(
                f"LLM API error {resp.status_code}: {error_detail}"
            )
        data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    return _parse_json_response(raw)


def call_llm_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    """
    Call OpenRouter LLM and return raw text response (no JSON parsing).
    """
    api_key = get_openrouter_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        if not resp.is_success:
            error_detail = resp.text[:500]
            raise RuntimeError(
                f"LLM API error {resp.status_code}: {error_detail}"
            )
        data = resp.json()

    return _clean_reasoning_output(data["choices"][0]["message"]["content"])
