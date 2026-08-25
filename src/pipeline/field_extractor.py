from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .schemas import TASK1_FIELDS
from .model_finder import ModelMatch
from .llm_client import call_llm


@dataclass
class ExtractedValue:
    """Result of field extraction."""
    field_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 0.0
    source: str = ""  # "table", "text", "llm", "merged", "missing"
    notes: Optional[str] = None


@dataclass
class ExtractionResult:
    """Complete extraction result for a document."""
    document_id: str
    model_match: ModelMatch
    column_index: int
    models_found: list[str] = field(default_factory=list)
    fields: dict[str, ExtractedValue] = field(default_factory=dict)
    merged_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    llm_calls_made: int = 0


# ── Schema field to datasheet row label mapping ─────────────────────

FIELD_TO_ROW_LABEL: dict[str, list[str]] = {
    "product.max_pv_input_power": ["Max. PV Input Power"],
    "product.max_pv_input_voltage": ["Max. PV Input Voltage"],
    "product.startup_voltage": ["Start-up Voltage"],
    "product.mppt_voltage_range": ["MPPT Voltage Range"],
    "product.rated_output_power": ["Rated AC Output Active Power"],
    "product.rated_output_current": ["Rated AC Output Current"],
    "product.rated_output_voltage": ["Rated Output Voltage/Range", "Rated Output Voltage"],
    "product.grid_frequency": ["Rated Output Grid Frequency/Range", "Rated Output Grid Frequency"],
    "product.max_efficiency": ["Max. Efficiency"],
    "product.euro_efficiency": ["Euro Efficiency"],
    "product.weight": ["Weight"],
    "product.ip_rating": ["Protection Rating", "IP Rating", "Ingress Protection"],
    "product.operating_temperature": ["Operating Temperature Range", "Operating Temperature"],
    "product.warranty": ["Warranty"],
    "product.topology": ["Inverter Topology"],
    "compliance.grid_standards": ["Grid Regulation"],
    "compliance.safety_emc_standards": ["Safety EMC/Standard", "Safety EMC"],
    "compliance.surge_protection": ["Surge Protection Level", "Surge Protection"],
    "protection.dc_reverse_polarity": ["DC Polarity Reverse Connection Protection"],
    "protection.ac_short_circuit": ["AC Output Short Circuit Protection"],
    "protection.thermal": ["Thermal Protection"],
    "protection.islanding": ["Island Protection Monitoring"],
}


# ── LLM prompts for missing fields ─────────────────────────────────

LLM_SYSTEM_PROMPT = """You are a technical datasheet extraction assistant.
Extract specific field values from solar inverter datasheet content.
Return ONLY a JSON object with field names as keys and extracted values.
If a field is not found, use null as the value."""

LLM_USER_PROMPT_TEMPLATE = """Extract the following field values from this datasheet.

Target model: {model_name} (column index: {col_idx})
Models in order: {models_list}

Datasheet content:
---
{content}
---

Fields to extract:
{fields_list}

Return JSON:
{{
  "field_name": "extracted value or null",
  ...
}}"""


def load_cached_page(doc_id: str, page_num: int) -> dict:
    """Load cached page data."""
    cache_path = Path("cache") / doc_id / "pages" / f"page_{page_num}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return {}


def load_cached_ocr(doc_id: str) -> dict:
    """Load cached OCR evidence."""
    ocr_path = Path("outputs") / f"ocr_evidence_{doc_id}.json"
    if ocr_path.exists():
        return json.loads(ocr_path.read_text())
    return {}


def parse_models_from_line(raw_text: str) -> list[str]:
    """Parse model names from raw text by splitting on spaces."""
    models = []
    seen = set()
    
    for line in raw_text.split("\n"):
        for word in line.split():
            word = word.strip()
            if "SUN" in word.upper() and "K" in word.upper():
                if word not in seen:
                    seen.add(word)
                    models.append(word)
    
    return models


def find_column_index(models: list[str], matched_model: str) -> int:
    """Find column index by matching model finder output with parsed models."""
    matched_upper = matched_model.upper().replace("-", "").replace(" ", "")
    
    for idx, model in enumerate(models):
        model_upper = model.upper().replace("-", "").replace(" ", "")
        if matched_upper == model_upper:
            return idx
    
    for idx, model in enumerate(models):
        if "/" in model:
            continue
        model_upper = model.upper().replace("-", "").replace(" ", "")
        if matched_upper in model_upper or model_upper in matched_upper:
            return idx
    
    return 0


def extract_unit_and_value(text: str) -> tuple[str, str]:
    """Extract unit and value from text like "(kW) 5.2 6.5" or "(V) 1100"."""
    text = text.strip()
    
    if text.startswith("("):
        end_paren = text.find(")")
        if end_paren != -1:
            unit = text[1:end_paren]
            remaining = text[end_paren + 1:].strip()
            return unit, remaining
    
    return "", text


# Fields where the value is the entire remaining text
FULL_TEXT_FIELDS = {
    "product.rated_output_voltage",
    "product.grid_frequency",
    "product.warranty",
    "product.topology",
    "compliance.grid_standards",
    "compliance.safety_emc_standards",
    "compliance.surge_protection",
}


def find_row_value(raw_text: str, row_labels: list[str], col_idx: int, field_name: str = "") -> Optional[tuple[str, str, str]]:
    """Find a value in raw text by row label and column position."""
    lines = raw_text.split("\n")
    
    for line in lines:
        line_lower = line.lower()
        for label in row_labels:
            if label.lower() in line_lower:
                label_pos = line.lower().find(label.lower())
                if label_pos == -1:
                    continue
                
                after_label = line[label_pos + len(label):].strip()
                
                if not after_label:
                    return None, "", "merged"
                
                unit, after_unit = extract_unit_and_value(after_label)
                after_label = after_unit
                
                if not after_label:
                    return None, unit, "merged"
                
                if field_name in FULL_TEXT_FIELDS:
                    return after_label, unit, "multi"
                
                values = after_label.split()
                
                if len(values) == 1:
                    return values[0], unit, "shared"
                
                if len(values) == 0:
                    return None, unit, "missing"
                
                if col_idx < len(values):
                    return values[col_idx], unit, "multi"
                else:
                    return None, unit, "merged"
    
    return None, "", "missing"


def extract_fields_from_text(
    raw_text: str,
    col_idx: int,
    field_labels: dict[str, list[str]],
) -> tuple[dict[str, ExtractedValue], list[str], list[str]]:
    """Extract all fields from raw text."""
    fields = {}
    merged = []
    missing = []
    
    for field_name, labels in field_labels.items():
        value, unit, extract_type = find_row_value(raw_text, labels, col_idx, field_name)
        
        if extract_type == "merged":
            merged.append(field_name)
            fields[field_name] = ExtractedValue(
                field_name=field_name,
                value=None,
                unit=unit,
                confidence=0.5,
                source="merged",
                notes="Value appears to be shared across models or merged cells",
            )
        elif extract_type == "missing" or value is None:
            missing.append(field_name)
            fields[field_name] = ExtractedValue(
                field_name=field_name,
                value=None,
                unit=unit,
                confidence=0.0,
                source="missing",
                notes="Field not found in document",
            )
        else:
            confidence = 0.9 if extract_type == "multi" else 0.8
            fields[field_name] = ExtractedValue(
                field_name=field_name,
                value=value,
                unit=unit,
                confidence=confidence,
                source="table",
            )
    
    return fields, merged, missing


# ── LLM fallback for missing fields ─────────────────────────────────

def _build_llm_prompt(
    model_match: ModelMatch,
    raw_text: str,
    missing_fields: list[str],
) -> tuple[str, str]:
    """Build prompts for LLM extraction of missing fields."""
    # Build fields list
    fields_list = "\n".join(f"- {f}" for f in missing_fields)
    
    # Truncate raw text to fit in prompt
    content = raw_text[:2000] if len(raw_text) > 2000 else raw_text
    
    user_prompt = LLM_USER_PROMPT_TEMPLATE.format(
        model_name=model_match.matched_model,
        col_idx=0,
        models_list=", ".join(["4K", "5K", "6K", "7K", "8K", "10K", "12K", "15K"]),
        content=content,
        fields_list=fields_list,
    )
    
    return LLM_SYSTEM_PROMPT, user_prompt


def _parse_llm_response(
    response: dict,
    missing_fields: list[str],
) -> dict[str, ExtractedValue]:
    """Parse LLM response into ExtractedValue objects."""
    results = {}
    
    for field_name in missing_fields:
        if field_name in response:
            value = response[field_name]
            if value is not None:
                results[field_name] = ExtractedValue(
                    field_name=field_name,
                    value=str(value),
                    confidence=0.7,
                    source="llm",
                    notes="Extracted by LLM (fallback)",
                )
            else:
                results[field_name] = ExtractedValue(
                    field_name=field_name,
                    value=None,
                    confidence=0.0,
                    source="missing",
                    notes="Not found by LLM",
                )
        else:
            results[field_name] = ExtractedValue(
                field_name=field_name,
                value=None,
                confidence=0.0,
                source="missing",
                notes="Field not in LLM response",
            )
    
    return results


def extract_missing_with_llm(
    model_match: ModelMatch,
    raw_text: str,
    missing_fields: list[str],
) -> tuple[dict[str, ExtractedValue], int]:
    """
    Use LLM to extract missing fields.
    Returns (extracted_fields, llm_calls_made).
    """
    if not missing_fields:
        return {}, 0
    
    try:
        system_prompt, user_prompt = _build_llm_prompt(model_match, raw_text, missing_fields)
        
        response = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )
        
        llm_results = _parse_llm_response(response, missing_fields)
        return llm_results, 1
        
    except Exception as e:
        # LLM failed - return missing fields with error note
        error_results = {}
        for field_name in missing_fields:
            error_results[field_name] = ExtractedValue(
                field_name=field_name,
                value=None,
                confidence=0.0,
                source="llm_error",
                notes=f"LLM extraction failed: {str(e)[:100]}",
            )
        return error_results, 1


# ── Main extraction function ────────────────────────────────────────

def extract_from_cached(
    doc_id: str,
    model_match: ModelMatch,
    pages: list[int] = None,
    use_llm_fallback: bool = True,
) -> ExtractionResult:
    """
    Extract field values from cached data.
    1. Rule-based extraction (free)
    2. LLM fallback for missing fields (if enabled)
    """
    if pages is None:
        pages = [2]
    
    result = ExtractionResult(
        document_id=doc_id,
        model_match=model_match,
        column_index=0,
    )
    
    # Combine raw text from all pages
    all_raw_text = ""
    for page_num in pages:
        page_data = load_cached_page(doc_id, page_num)
        if page_data:
            all_raw_text += page_data.get("raw_text", "") + "\n"
    
    # Also try OCR text as fallback
    ocr_data = load_cached_ocr(doc_id)
    for page_key, page_info in ocr_data.get("pages", {}).items():
        all_raw_text += page_info.get("raw_text", "") + "\n"
    
    # Parse models from text
    models_found = parse_models_from_line(all_raw_text)
    result.models_found = models_found
    
    # Find column index
    if models_found and model_match.matched_model:
        col_idx = find_column_index(models_found, model_match.matched_model)
        result.column_index = col_idx
    
    # Rule-based extraction
    fields, merged, missing = extract_fields_from_text(
        all_raw_text, result.column_index, FIELD_TO_ROW_LABEL
    )
    
    result.fields = fields
    result.merged_fields = merged
    result.missing_fields = missing
    
    # LLM fallback for missing fields
    if use_llm_fallback and missing:
        llm_fields, llm_calls = extract_missing_with_llm(
            model_match, all_raw_text, missing
        )
        result.fields.update(llm_fields)
        result.llm_calls_made = llm_calls
        
        # Update missing list (only fields still missing after LLM)
        result.missing_fields = [
            f for f in missing
            if f in llm_fields and llm_fields[f].source == "missing"
        ]
    
    return result


def print_extraction_result(result: ExtractionResult):
    """Print extraction results in a readable format."""
    print(f"\nExtraction Results:")
    print(f"  Document: {result.document_id}")
    print(f"  Target: {result.model_match.matched_model}")
    print(f"  Column index: {result.column_index}")
    print(f"  Models found: {result.models_found}")
    print(f"  LLM calls made: {result.llm_calls_made}")
    
    # Group by source
    table = {k: v for k, v in result.fields.items() if v.source == "table"}
    llm = {k: v for k, v in result.fields.items() if v.source == "llm"}
    merged = {k: v for k, v in result.fields.items() if v.source == "merged"}
    missing = {k: v for k, v in result.fields.items() if v.source in ("missing", "llm_error")}
    
    print(f"\n  Table extraction ({len(table)}):")
    for field_name, val in sorted(table.items()):
        unit_str = f" {val.unit}" if val.unit else ""
        print(f"    {field_name}: {val.value}{unit_str}")
    
    if llm:
        print(f"\n  LLM extraction ({len(llm)}):")
        for field_name, val in sorted(llm.items()):
            print(f"    {field_name}: {val.value}")
    
    if merged:
        print(f"\n  Merged/Shared ({len(merged)}):")
        for field_name, val in sorted(merged.items()):
            unit_str = f" {val.unit}" if val.unit else ""
            print(f"    {field_name}: {val.notes} {unit_str}")
    
    if missing:
        print(f"\n  Missing ({len(missing)}):")
        for field_name in sorted(missing):
            print(f"    {field_name}")
