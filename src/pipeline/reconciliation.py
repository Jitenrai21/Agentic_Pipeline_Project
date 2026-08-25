from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .schemas import TASK1_FIELDS
from .llm_client import call_llm


@dataclass
class FieldReconciliation:
    """Reconciliation result for a single field."""
    field_name: str
    status: str  # "verified", "conflict", "source_only", "missing", "variant_diff"
    value_a: Optional[str] = None
    value_b: Optional[str] = None
    source_a: Optional[str] = None
    source_b: Optional[str] = None
    variant_a: Optional[str] = None
    variant_b: Optional[str] = None
    confidence: float = 0.0
    resolution: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ReconciliationResult:
    """Complete reconciliation result."""
    fields: dict[str, FieldReconciliation] = field(default_factory=dict)
    agreements: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    source_only: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    llm_calls_made: int = 0


# ── LLM prompts for reconciliation ─────────────────────────────────

RECONCILE_SYSTEM_PROMPT = """You are a technical document comparison assistant.
Compare field values from two datasheet sources and determine if they agree or conflict.
Return ONLY a JSON object with reconciliation results for each field."""

RECONCILE_USER_PROMPT_TEMPLATE = """Compare the following field values from two sources.

{comparisons}

For each field, determine:
1. Do the values represent the same thing? (account for format differences)
2. Is there a real conflict or just notation difference?
3. What is the correct reconciliation status?

Return JSON:
{{
  "reconciliations": [
    {{
      "field": "field_name",
      "status": "verified" or "conflict" or "variant_diff",
      "reason": "brief explanation",
      "normalized_value": "if values are equivalent, the canonical form"
    }}
  ]
}}"""


def _normalize_value(value: str) -> str:
    """Normalize value for comparison."""
    if value is None:
        return ""
    return value.strip().lower().replace(" ", "")


def _compare_values(val_a: str, val_b: str) -> tuple[bool, str]:
    """
    Compare two values and determine if they match.
    Returns (is_match, reason).
    """
    if val_a is None and val_b is None:
        return True, "Both missing"
    
    if val_a is None or val_b is None:
        return False, "One source missing"
    
    norm_a = _normalize_value(val_a)
    norm_b = _normalize_value(val_b)
    
    # Exact match
    if norm_a == norm_b:
        return True, "Exact match"
    
    # One contains the other
    if norm_a in norm_b or norm_b in norm_a:
        return True, "Partial match (one contains the other)"
    
    # Format differences (with/without units, %, etc.)
    # Remove common suffixes for comparison
    clean_a = norm_a.replace("%", "").replace("kg", "").replace("v", "").replace("a", "")
    clean_b = norm_b.replace("%", "").replace("kg", "").replace("v", "").replace("a", "")
    
    if clean_a == clean_b:
        return True, "Format difference (units/symbols)"
    
    return False, "Values differ"


def reconcile_fields(
    fields_a: dict[str, dict],
    fields_b: dict[str, dict],
    variant_a: str = "",
    variant_b: str = "",
    use_llm: bool = True,
) -> ReconciliationResult:
    """
    Reconcile fields from two sources.
    
    Args:
        fields_a: Extracted fields from source A {field_name: {value, unit, ...}}
        fields_b: Extracted fields from source B {field_name: {value, unit, ...}}
        variant_a: Variant name for source A
        variant_b: Variant name for source B
        use_llm: Whether to use LLM for ambiguous cases
    """
    result = ReconciliationResult()
    ambiguous = []
    
    for field_name in TASK1_FIELDS:
        val_a = fields_a.get(field_name, {}).get("value")
        val_b = fields_b.get(field_name, {}).get("value")
        
        # Get unit if present
        unit_a = fields_a.get(field_name, {}).get("unit", "")
        unit_b = fields_b.get(field_name, {}).get("unit", "")
        
        # Format values with units for comparison
        display_a = f"{val_a} {unit_a}".strip() if val_a else None
        display_b = f"{val_b} {unit_b}".strip() if val_b else None
        
        # Case 1: Both missing
        if val_a is None and val_b is None:
            result.fields[field_name] = FieldReconciliation(
                field_name=field_name,
                status="missing",
                confidence=1.0,
                notes="Not found in either source",
            )
            result.missing.append(field_name)
            continue
        
        # Case 2: Only in one source
        if val_a is None:
            result.fields[field_name] = FieldReconciliation(
                field_name=field_name,
                status="source_only",
                value_b=display_b,
                source_b="source_2",
                variant_b=variant_b,
                confidence=0.9,
                notes=f"Only found in {variant_b or 'source_2'}",
            )
            result.source_only.append(field_name)
            continue
        
        if val_b is None:
            result.fields[field_name] = FieldReconciliation(
                field_name=field_name,
                status="source_only",
                value_a=display_a,
                source_a="source_1",
                variant_a=variant_a,
                confidence=0.9,
                notes=f"Only found in {variant_a or 'source_1'}",
            )
            result.source_only.append(field_name)
            continue
        
        # Case 3: Both have values - compare
        is_match, reason = _compare_values(display_a, display_b)
        
        if is_match:
            result.fields[field_name] = FieldReconciliation(
                field_name=field_name,
                status="verified",
                value_a=display_a,
                value_b=display_b,
                source_a="source_1",
                source_b="source_2",
                variant_a=variant_a,
                variant_b=variant_b,
                confidence=0.95,
                notes=reason,
            )
            result.agreements.append(field_name)
        else:
            # Ambiguous - needs LLM or flag as conflict
            ambiguous.append({
                "field": field_name,
                "value_a": display_a,
                "value_b": display_b,
                "variant_a": variant_a,
                "variant_b": variant_b,
            })
    
    # LLM for ambiguous cases
    if ambiguous and use_llm:
        llm_results = _llm_reconcile_batch(ambiguous)
        result.llm_calls_made = 1
        
        for field_name, reconciliation in llm_results.items():
            result.fields[field_name] = reconciliation
            if reconciliation.status == "verified":
                result.agreements.append(field_name)
            elif reconciliation.status in ("conflict", "variant_diff"):
                result.conflicts.append(field_name)
    elif ambiguous:
        # No LLM - mark all ambiguous as conflicts
        for item in ambiguous:
            field_name = item["field"]
            result.fields[field_name] = FieldReconciliation(
                field_name=field_name,
                status="conflict",
                value_a=item["value_a"],
                value_b=item["value_b"],
                variant_a=item["variant_a"],
                variant_b=item["variant_b"],
                confidence=0.5,
                notes="Values differ - manual review needed",
            )
            result.conflicts.append(field_name)
    
    return result


def _llm_reconcile_batch(ambiguous: list[dict]) -> dict[str, FieldReconciliation]:
    """Use LLM to reconcile ambiguous field values."""
    if not ambiguous:
        return {}
    
    # Build comparison text
    comparisons = []
    for item in ambiguous:
        comparisons.append(
            f"Field: {item['field']}\n"
            f"  Source A ({item['variant_a']}): {item['value_a']}\n"
            f"  Source B ({item['variant_b']}): {item['value_b']}"
        )
    
    comparisons_text = "\n\n".join(comparisons)
    
    user_prompt = RECONCILE_USER_PROMPT_TEMPLATE.format(
        comparisons=comparisons_text
    )
    
    try:
        response = call_llm(
            system_prompt=RECONCILE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
        )
        
        # Parse response
        reconciliations = response.get("reconciliations", [])
        results = {}
        
        for item in reconciliations:
            field_name = item.get("field", "")
            status = item.get("status", "conflict")
            reason = item.get("reason", "")
            
            # Find original data
            original = next((a for a in ambiguous if a["field"] == field_name), None)
            if original:
                results[field_name] = FieldReconciliation(
                    field_name=field_name,
                    status=status,
                    value_a=original["value_a"],
                    value_b=original["value_b"],
                    variant_a=original["variant_a"],
                    variant_b=original["variant_b"],
                    confidence=0.85,
                    notes=reason,
                )
        
        return results
        
    except Exception as e:
        # LLM failed - mark all as conflicts
        results = {}
        for item in ambiguous:
            results[item["field"]] = FieldReconciliation(
                field_name=item["field"],
                status="conflict",
                value_a=item["value_a"],
                value_b=item["value_b"],
                variant_a=item["variant_a"],
                variant_b=item["variant_b"],
                confidence=0.5,
                notes=f"LLM reconciliation failed: {str(e)[:50]}",
            )
        return results


def print_reconciliation(result: ReconciliationResult):
    """Print reconciliation results."""
    print(f"\nReconciliation Results:")
    print(f"  Agreements: {len(result.agreements)}")
    print(f"  Conflicts: {len(result.conflicts)}")
    print(f"  Source only: {len(result.source_only)}")
    print(f"  Missing: {len(result.missing)}")
    print(f"  LLM calls: {result.llm_calls_made}")
    
    if result.agreements:
        print(f"\n  Agreements:")
        for field in result.agreements:
            rec = result.fields[field]
            print(f"    {field}: {rec.value_a} = {rec.value_b}")
    
    if result.conflicts:
        print(f"\n  Conflicts:")
        for field in result.conflicts:
            rec = result.fields[field]
            print(f"    {field}:")
            print(f"      {rec.variant_a}: {rec.value_a}")
            print(f"      {rec.variant_b}: {rec.value_b}")
            print(f"      Reason: {rec.notes}")
