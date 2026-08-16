import json
import os
import re
import time
from pathlib import Path

from .schemas import Comparison, Status


def _fmt_value(v) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _render_markdown(comparisons: list[Comparison],
                     target_model: str,
                     source_labels: dict[str, str]) -> str:
    lines = [
        f"# Import draft — {target_model}",
        "",
        "Comparison of two Deye datasheet variants. Values are extracted from the PDF",
        "text layer; a merged/shared cell means one value applies to several models.",
        "",
        "## Field comparison",
        "",
        "| Field | Status | Confidence | Source 1 | Source 2 | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for c in comparisons:
        def cell(sv):
            if sv is None:
                return ""
            unit = f" {sv.unit}" if sv.unit else ""
            return f"{_fmt_value(sv.value)}{unit}"
        notes = c.notes.replace("|", "\\|")
        lines.append(
            f"| {c.field} | {c.status.value} | {c.confidence.value} "
            f"| {cell(c.source_1)} | {cell(c.source_2)} | {notes} |"
        )

    conflicts = [c for c in comparisons if c.status == Status.CONFLICT]
    only1 = [c for c in comparisons if c.status == Status.SOURCE_1_ONLY]
    only2 = [c for c in comparisons if c.status == Status.SOURCE_2_ONLY]
    uncertain = [c for c in comparisons if c.status == Status.UNCERTAIN]

    lines += ["", "## Conflicts", ""]
    if conflicts:
        for c in conflicts:
            lines.append(f"- **{c.field}**: "
                         f"{source_labels.get(c.source_1.source_id, c.source_1.source_id)} "
                         f"= {_fmt_value(c.source_1.value)} vs "
                         f"{source_labels.get(c.source_2.source_id, c.source_2.source_id)} "
                         f"= {_fmt_value(c.source_2.value)}. {c.notes}")
    else:
        lines.append("- none")

    lines += ["", "## Present in one source only", ""]
    for label, items in (("Source 1", only1), ("Source 2", only2)):
        if items:
            lines.append(f"**{label}**")
            for c in items:
                src = c.source_1 if c.source_1 else c.source_2
                lines.append(f"- {c.field} = {_fmt_value(src.value)}. {c.notes}")
        else:
            lines.append(f"- {label}: none")

    lines += ["", "## Unclear / low confidence", ""]
    if uncertain:
        for c in uncertain:
            lines.append(f"- {c.field}: {c.notes}")
    else:
        lines.append("- none")

    lines += ["", "## Recommended verification questions", ""]
    for c in conflicts:
        lines.append(
            f"- {c.field}: which value applies to {target_model}? "
            f"({_fmt_value(c.source_1.value)} vs {_fmt_value(c.source_2.value)})")
    return "\n".join(lines) + "\n"


def _compact(comparisons: list[Comparison]) -> list[dict]:
    """Shrinks comparisons for the LLM payload"""
    out = []
    for c in comparisons:
        item: dict = {"field": c.field, "status": c.status.value,
                      "confidence": c.confidence.value}
        for key in ("source_1", "source_2"):
            sv = getattr(c, key)
            if sv is None:
                item[key] = None
            else:
                item[key] = {"value": sv.value, "unit": sv.unit}
        if c.notes:
            item["notes"] = c.notes[:120]
        out.append(item)
    return out


def _strip_thinking(text: str) -> str:
    """Drop a reasoning-model thinking block (delimiter: a closing tag).

    Cuts after the LAST closing marker so truncated reasoning (where the model
    ran out of tokens mid-block) is removed too. If the text looks like a pure
    thinking block with no closing marker, returns an empty string (nothing
    usable survived).
    """
    lines = text.splitlines()
    markers = (" response", "</thinking>", "response")
    last = -1
    for i, line in enumerate(lines):
        clean = "".join(ch for ch in line if ch.isprintable()).strip()
        if clean in markers:
            last = i
    if last >= 0:
        return "\n".join(lines[last + 1:]).strip()
    first = "".join(ch for ch in lines[0] if ch.isprintable()).strip() if lines else ""
    if first.startswith(("thinking", "<thinking", " response", "response")):
        return ""
    return text.strip()


def _llm_markdown(comparisons: list[Comparison], target_model: str,
                  source_labels: dict[str, str], client) -> str:
    system = (
        "You are a datasheet comparison reporter. Produce an import draft markdown report "
        "from the JSON comparison data I provide. Sections, in order: "
        "1) a field comparison table (columns: Field, Status, Confidence, Source 1, Source 2, Notes), "
        "2) Conflicts, 3) Present in one source only, "
        "4) Unclear / low confidence, 5) Recommended verification questions. "
        "Base every statement strictly on the provided data; never invent values. "
        "Do NOT include any thinking, reasoning, or explanation; output only the markdown report."
    )
    user = json.dumps({
        "target_model": target_model,
        "source_labels": source_labels,
        "fields": _compact(comparisons),
    }, ensure_ascii=False, indent=2)
    for attempt in range(2):
        resp = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=6000,
        )
        md = _strip_thinking(resp.choices[0].message.content or "")
        finished = getattr(resp.choices[0], "finish_reason", "") != "length"
        complete = finished and "verification" in md.lower()
        if complete:
            return md.strip() + "\n"
        if attempt == 0:
            time.sleep(3)
    if not md:
        raise RuntimeError("LLM report produced no usable content (truncated reasoning block)")
    raise RuntimeError("LLM report incomplete after retries")


def report(comparisons: list[Comparison], target_model: str,
           output_dir: Path, source_labels: dict[str, str],
           client=None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_model": target_model,
        "source_labels": source_labels,
        "fields": [c.model_dump(mode="json") for c in comparisons],
    }
    (output_dir / "structured_output.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if client is None and os.environ.get("GROQ_API_KEY"):
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
    if client is not None:
        try:
            md = _llm_markdown(comparisons, target_model, source_labels, client)
        except Exception as exc:
            err = str(exc)
            reason = ("Groq rate limit / quota exceeded" if
                      ("429" in err or "rate_limit" in err.lower()) else
                      err[:120])
            md = f"> Note: LLM report generation was unavailable ({reason}); deterministic report below.\n\n"
            md += _render_markdown(comparisons, target_model, source_labels)
    else:
        md = _render_markdown(comparisons, target_model, source_labels)
    (output_dir / "import_draft.md").write_text(md, encoding="utf-8")
    return payload