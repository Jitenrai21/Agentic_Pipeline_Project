from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .llm_client import call_llm
from .evidence_layer import EvidenceBlock


@dataclass
class ModelMatch:
    """Result of model identification."""
    requested: str
    matched_model: str
    variant: str
    confidence: float
    source_document: str
    notes: Optional[str] = None


SYSTEM_PROMPT = """You are a technical document analysis assistant.
You identify product model numbers and variants from datasheet content.
You are given raw text extracted from a product datasheet.
Your job is to find all model numbers mentioned, and determine which one
matches what the user is asking for.
Return ONLY a JSON object with the specified structure."""

USER_PROMPT_TEMPLATE = """Analyze the following datasheet content and identify the target product.

User requested: {requested_model}

Datasheet content:
---
{content}
---

Tasks:
1. List ALL model numbers / product identifiers you can find in the content above.
2. Determine which model best matches what the user requested: "{requested_model}"
3. Identify the variant or suffix if present.
4. Rate your confidence (0.0 to 1.0).
5. If there is ambiguity or the match is uncertain, explain why.

Return JSON:
{{
  "all_models_found": ["model1", "model2", ...],
  "requested": "{requested_model}",
  "matched_model": "exact model string from document that best matches",
  "variant": "variant suffix or empty string if none",
  "confidence": 0.95,
  "reasoning": "brief explanation of how you determined the match"
}}"""


def _extract_content(
    blocks: list[EvidenceBlock], max_chars: int = 4000
) -> str:
    """Extract text content from evidence blocks for LLM analysis."""
    relevant = []
    total = 0
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if total + len(text) > max_chars:
            break
        relevant.append(text)
        total += len(text)
    return "\n".join(relevant)


def find_target_model(
    requested_model: str,
    document_id: str,
    blocks: dict[int, list[EvidenceBlock]],
) -> ModelMatch:
    """
    Use LLM to identify the target model from evidence blocks.
    No hardcoded regex -- the LLM handles all pattern recognition.
    """
    all_blocks = []
    for page_blocks in blocks.values():
        all_blocks.extend(page_blocks)

    content = _extract_content(all_blocks)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        requested_model=requested_model,
        content=content,
    )

    result = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
    )

    return ModelMatch(
        requested=result.get("requested", requested_model),
        matched_model=result.get("matched_model", ""),
        variant=result.get("variant", ""),
        confidence=result.get("confidence", 0.0),
        source_document=document_id,
        notes=result.get("reasoning", ""),
    )


def find_target_model_all_sources(
    requested_model: str,
    all_sources: dict[str, dict[int, list[EvidenceBlock]]],
) -> list[ModelMatch]:
    """
    Identify target model across all source documents.
    """
    results = []
    for doc_id, blocks in all_sources.items():
        match = find_target_model(
            requested_model=requested_model,
            document_id=doc_id,
            blocks=blocks,
        )
        results.append(match)
    return results
