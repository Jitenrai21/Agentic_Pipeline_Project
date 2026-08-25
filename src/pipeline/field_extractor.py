from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .schemas import TASK1_FIELDS
from .model_finder import ModelMatch, find_target_model


@dataclass
class ExtractedValue:
    """Result of field extraction."""
    field_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 0.0
    source: str = ""  # "table", "text", "missing"
    notes: Optional[str] = None


@dataclass
class ExtractionResult:
    """Complete extraction result for a document."""
    document_id: str
    model_match: ModelMatch
    column_index: int
    models_found: list[str] = field(default_factory=list)
    fields: dict[str, ExtractedValue] = field(default_factory=dict)


# ── Schema field to datasheet row label mapping ─────────────────────

FIELD_TO_ROW_LABEL: dict[str, list[str]] = {
    "product.max_pv_input_power": ["Max. PV Input Power"],
    "product.max_pv_input_voltage": ["Max. PV Input Voltage"],
    "product.startup_voltage": ["Start-up Voltage"],
    "product.mppt_voltage_range": ["MPPT Voltage Range"],
    "product.rated_output_power": ["Rated AC Output Active Power"],
    "product.rated_output_current": ["Rated AC Output Current"],
    "product.rated_output_voltage": ["Rated Output Voltage"],
    "product.grid_frequency": ["Rated Output Grid Frequency"],
    "product.max_efficiency": ["Max. Efficiency"],
    "product.euro_efficiency": ["Euro Efficiency"],
    "product.weight": ["Weight"],
    "product.ip_rating": ["Protection Rating"],
    "product.operating_temperature": ["Operating Temperature"],
    "product.warranty": ["Warranty"],
    "product.topology": ["Inverter Topology"],
    "compliance.grid_standards": ["Grid Regulation"],
    "compliance.safety_emc_standards": ["Safety EMC/Standard"],
    "compliance.surge_protection": ["Surge Protection"],
    "protection.dc_reverse_polarity": ["DC Polarity Reverse Connection Protection"],
    "protection.ac_short_circuit": ["AC Output Short Circuit Protection"],
    "protection.thermal": ["Thermal Protection"],
    "protection.islanding": ["Island Protection Monitoring"],
}


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
    """
    Parse model names from raw text by splitting on spaces.
    No regex - pure string operations.
    """
    models = []
    seen = set()
    
    # Split by lines first
    for line in raw_text.split("\n"):
        # Split each line by spaces
        for word in line.split():
            word = word.strip()
            # Check if it looks like a model name
            if "SUN" in word.upper() and "K" in word.upper():
                if word not in seen:
                    seen.add(word)
                    models.append(word)
    
    return models


def find_column_index(models: list[str], matched_model: str) -> int:
    """
    Find column index by matching model finder output with parsed models.
    No regex - pure string comparison.
    """
    # Normalize for comparison
    matched_upper = matched_model.upper().replace("-", "").replace(" ", "")
    
    # First pass: exact match
    for idx, model in enumerate(models):
        model_upper = model.upper().replace("-", "").replace(" ", "")
        if matched_upper == model_upper:
            return idx
    
    # Second pass: model must be a proper individual model (not a combined range)
    for idx, model in enumerate(models):
        # Skip combined models like "SUN-4/5/6/7/8/10/12/15K-GO6P3"
        if "/" in model:
            continue
        model_upper = model.upper().replace("-", "").replace(" ", "")
        if matched_upper in model_upper or model_upper in matched_upper:
            return idx
    
    return 0


def find_row_value(raw_text: str, row_labels: list[str], col_idx: int) -> Optional[tuple[str, str]]:
    """
    Find a value in raw text by row label and column position.
    Returns (value, unit) or None.
    """
    lines = raw_text.split("\n")
    
    for line in lines:
        line_lower = line.lower()
        for label in row_labels:
            if label.lower() in line_lower:
                # Find the label position and extract values after it
                label_pos = line.lower().find(label.lower())
                if label_pos == -1:
                    continue
                
                after_label = line[label_pos + len(label):].strip()
                
                # Extract unit if present (in parentheses)
                unit = ""
                if after_label.startswith("("):
                    end_paren = after_label.find(")")
                    if end_paren != -1:
                        unit = after_label[1:end_paren]
                        after_label = after_label[end_paren + 1:].strip()
                
                # Split remaining text into values
                values = after_label.split()
                
                if col_idx < len(values):
                    return values[col_idx], unit
                elif len(values) == 1:
                    # Single value shared across all models
                    return values[0], unit
    
    return None


def extract_from_cached(
    doc_id: str,
    model_match: ModelMatch,
    pages: list[int] = None,
) -> ExtractionResult:
    """
    Extract field values from cached data using model finder output.
    No LLM calls in extraction - uses model finder result.
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
    
    # Also try OCR text
    ocr_data = load_cached_ocr(doc_id)
    for page_key, page_info in ocr_data.get("pages", {}).items():
        all_raw_text += page_info.get("raw_text", "") + "\n"
    
    # Parse models from text
    models_found = parse_models_from_line(all_raw_text)
    result.models_found = models_found
    
    # Find column index using model finder output
    if models_found and model_match.matched_model:
        col_idx = find_column_index(models_found, model_match.matched_model)
        result.column_index = col_idx
    
    # Extract fields using schema mapping
    for field_name in TASK1_FIELDS:
        row_labels = FIELD_TO_ROW_LABEL.get(field_name, [])
        if not row_labels:
            continue
        
        extracted = find_row_value(all_raw_text, row_labels, result.column_index)
        if extracted:
            value, unit = extracted
            result.fields[field_name] = ExtractedValue(
                field_name=field_name,
                value=value,
                unit=unit,
                confidence=0.9,
                source="table",
            )
    
    return result


def print_extraction_result(result: ExtractionResult):
    """Print extraction results in a readable format."""
    print(f"\nExtraction Results:")
    print(f"  Document: {result.document_id}")
    print(f"  Target: {result.model_match.matched_model}")
    print(f"  Column index: {result.column_index}")
    print(f"  Models found: {result.models_found}")
    print(f"\n  Extracted fields ({len(result.fields)}):")
    for field_name, extracted in sorted(result.fields.items()):
        unit_str = f" {extracted.unit}" if extracted.unit else ""
        print(f"    {field_name}: {extracted.value}{unit_str} ({extracted.source})")
