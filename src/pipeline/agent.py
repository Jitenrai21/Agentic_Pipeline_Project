import json
import os
import time

from .mapper import FIELDS, map_evidence
from .normalizer import normalize
from .schemas import CanonicalValue, Confidence, EvidenceRecord

class AgentError(RuntimeError):
    pass

FIELD_NAMES = [s.field for s in FIELDS]
SPEC_BY_FIELD = {s.field: s for s in FIELDS}

def _system_prompt(target_model: str) -> str:
    return (
        "You are an evidence interpreter for a datasheet comparison pipeline. "
        "For each extracted evidence record you must decide which canonical field it maps to.\n"
        "Rules:\n"
        "- 'field' MUST be exactly one of: " + ", ".join(FIELD_NAMES) + " or null.\n"
        "- null means the record does not correspond to any canonical field.\n"
        "- Do NOT invent or modify values; you only classify the field.\n"
        "- If the label is garbled or unreadable, return null.\n"
        "- Return ONLY a JSON object with key 'assignments' containing an array; "
        "each element has keys: index, field, confidence, interpretation.\n"
        "- 'confidence' is one of: high, medium, low.\n"
        f"- Target model is {target_model}. A record may apply to it even when is_merged is true "
        "(the merged cell covers it).\n"
    )


def _records_payload(evidence: list[EvidenceRecord], offset: int = 0) -> list[dict]:
    return [
        {"index": offset + i, "source_id": e.source_id, "page": e.page,
         "raw_label": e.raw_label, "raw_value": e.raw_value,
         "model": e.model, "is_merged": e.is_merged, "notes": e.notes}
        for i, e in enumerate(evidence)
    ]


def _call_llm(client, system: str, user: str, retries: int = 2) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=4096,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            last = exc
            if attempt < retries and "rate_limit" in str(exc).lower():
                time.sleep(10 * (attempt + 1))
            else:
                raise
    raise last  # pragma: no cover

def _parse_assignments(text: str) -> list[dict]:
    dec = json.JSONDecoder()
    idx, n = 0, len(text)
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = dec.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for val in obj.values():
                if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                    return val
        idx = end
    raise AgentError("no valid JSON array of assignments found in LLM response")

def interpret(evidence: list[EvidenceRecord], target_model: str,
              client=None, chunk_size: int = 10, pause_s: float = 10.0,
              retries: int = 2) -> list[CanonicalValue]:
    """Interpret evidence into canonical values.

    If GROQ_API_KEY is set, the LLM assigns fields + confidence (values are
    still typed deterministically by the normalizer). Evidence is sent in
    chunks to stay within the provider's token-per-minute limit. Otherwise the
    deterministic mapper is used as fallback.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return map_evidence(evidence, target_model)

    if client is None:
        from groq import Groq
        client = Groq(api_key=api_key)

    system = _system_prompt(target_model)
    try:
        assignments: list[dict] = []
        for start in range(0, len(evidence), chunk_size):
            chunk = evidence[start:start + chunk_size]
            text = _call_llm(client, system,
                             json.dumps(_records_payload(chunk, offset=start),
                                        ensure_ascii=False),
                             retries=retries)
            assignments += _parse_assignments(text)
            if start + chunk_size < len(evidence):
                time.sleep(pause_s)
    except Exception as exc:
        print(f"[agent] LLM interpretation failed ({exc}); "
              "falling back to deterministic mapper")
        return map_evidence(evidence, target_model)
    by_index = {a.get("index"): a for a in assignments}

    out: list[CanonicalValue] = []
    for i, ev in enumerate(evidence):
        a = by_index.get(i)
        if not a or not a.get("field"):
            continue
        spec = SPEC_BY_FIELD.get(a["field"])
        if spec is None:
            continue
        value, note = normalize(spec.value_type, ev.raw_value)
        if value is None:
            continue
        try:
            conf = Confidence(a.get("confidence", "low"))
        except ValueError:
            conf = Confidence.LOW
        notes = "; ".join(filter(None, [
            f"llm: {a.get('interpretation', '')}", note, ev.notes]))
        out.append(CanonicalValue(
            field=spec.field, source_id=ev.source_id, page=ev.page,
            raw=ev.raw_value, value=value, unit=spec.unit,
            confidence=conf, notes=notes, evidence_index=i,
        ))
    return out