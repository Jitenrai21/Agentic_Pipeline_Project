from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .schemas import TASK1_FIELDS
from .model_finder import ModelMatch
from .field_extractor import ExtractedValue, ExtractionResult, FIELD_TO_ROW_LABEL


@dataclass
class SpatialBlock:
    """A text block with spatial coordinates."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0
    
    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2
    
    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class SpatialRow:
    """A row of values at the same y-coordinate."""
    y_center: float
    blocks: list[SpatialBlock] = field(default_factory=list)
    
    @property
    def blocks_by_x(self) -> list[SpatialBlock]:
        """Return blocks sorted by x-coordinate."""
        return sorted(self.blocks, key=lambda b: b.x0)


def load_pdfplumber_words(doc_id: str, page_num: int) -> list[SpatialBlock]:
    """Load words from pdfplumber cache with precise coordinates."""
    cache_path = Path("cache") / doc_id / "pages" / f"page_{page_num}.json"
    if not cache_path.exists():
        return []
    
    data = json.loads(cache_path.read_text())
    words = data.get("words", [])
    
    blocks = []
    for word in words:
        blocks.append(SpatialBlock(
            text=word.get("text", ""),
            x0=word.get("x0", 0),
            y0=word.get("y0", 0),
            x1=word.get("x1", 0),
            y1=word.get("y1", 0),
            confidence=1.0,
        ))
    
    return blocks


def load_evidence_blocks(doc_id: str, page_num: int) -> list[SpatialBlock]:
    """Load spatial blocks from evidence JSON (fallback)."""
    evidence_path = Path("outputs") / f"ocr_evidence_{doc_id}.json"
    if not evidence_path.exists():
        return []
    
    data = json.loads(evidence_path.read_text())
    page_key = f"page_{page_num}"
    page_data = data.get("pages", {}).get(page_key, {})
    raw_blocks = page_data.get("blocks", [])
    
    blocks = []
    for block in raw_blocks:
        if block.get("block_type") != "text":
            continue
        bbox = block.get("bbox", [])
        if len(bbox) != 4:
            continue
        blocks.append(SpatialBlock(
            text=block.get("text", ""),
            x0=bbox[0],
            y0=bbox[1],
            x1=bbox[2],
            y1=bbox[3],
            confidence=block.get("confidence", 0),
        ))
    
    return blocks


def _cluster_blocks_into_rows(
    blocks: list[SpatialBlock],
    y_threshold: float = 5.0,
) -> list[SpatialRow]:
    """Cluster blocks into rows based on y-coordinate proximity."""
    if not blocks:
        return []
    
    sorted_blocks = sorted(blocks, key=lambda b: b.y0)
    rows: list[SpatialRow] = []
    current_row = SpatialRow(y_center=sorted_blocks[0].center_y)
    current_row.blocks.append(sorted_blocks[0])
    
    for block in sorted_blocks[1:]:
        if abs(block.center_y - current_row.y_center) <= y_threshold:
            current_row.blocks.append(block)
        else:
            rows.append(current_row)
            current_row = SpatialRow(y_center=block.center_y)
            current_row.blocks.append(block)
    
    rows.append(current_row)
    return rows


def _find_label_block(
    rows: list[SpatialRow],
    label: str,
) -> Optional[tuple[SpatialBlock, SpatialRow]]:
    """Find a block containing the label text and its row."""
    label_lower = label.lower()
    
    for row in rows:
        for block in row.blocks:
            if label_lower in block.text.lower():
                return block, row
    
    return None


def _find_label_block_multi_word(
    rows: list[SpatialRow],
    label: str,
) -> Optional[tuple[SpatialBlock, SpatialRow]]:
    """Find label by matching multiple words in sequence."""
    label_words = label.lower().split()
    
    for row in rows:
        blocks = row.blocks_by_x
        for i in range(len(blocks) - len(label_words) + 1):
            match = True
            for j, lw in enumerate(label_words):
                if i + j >= len(blocks):
                    match = False
                    break
                if lw not in blocks[i + j].text.lower():
                    match = False
                    break
            if match:
                combined_text = " ".join(b.text for b in blocks[i:i+len(label_words)])
                return SpatialBlock(
                    text=combined_text,
                    x0=blocks[i].x0,
                    y0=blocks[i].y0,
                    x1=blocks[i+len(label_words)-1].x1,
                    y1=blocks[i+len(label_words)-1].y1,
                ), row
    
    return None


def _extract_unit(text: str, label: str) -> tuple[str, str]:
    """Extract unit from text after removing label."""
    text = text.strip()
    
    if text.startswith("("):
        end_paren = text.find(")")
        if end_paren != -1:
            unit = text[1:end_paren]
            remaining = text[end_paren + 1:].strip()
            return unit, remaining
    
    return "", text


def _find_value_at_column(
    row: SpatialRow,
    col_idx: int,
    min_x: float = 0,
    max_blocks: int = 20,
) -> Optional[str]:
    """Find value at specific column index in the row."""
    blocks = row.blocks_by_x
    
    value_blocks = []
    for block in blocks:
        if block.x0 >= min_x:
            text = block.text.strip()
            if text and not text.startswith("("):
                value_blocks.append(text)
    
    if col_idx < len(value_blocks):
        return value_blocks[col_idx]
    
    return None


def find_row_value_spatial(
    rows: list[SpatialRow],
    label: str,
    col_idx: int,
    field_name: str = "",
) -> Optional[tuple[str, str, str]]:
    """Find a value using spatial coordinates."""
    result = _find_label_block(rows, label)
    
    if result is None:
        result = _find_label_block_multi_word(rows, label)
    
    if result is None:
        return None, "", "missing"
    
    label_block, row = result
    
    # Extract unit from label block text
    label_text = label_block.text
    unit = ""
    
    for lbl in [label, label.split("/")[0]]:
        idx = label_text.lower().find(lbl.lower())
        if idx != -1:
            after_label = label_text[idx + len(lbl):].strip()
            unit, _ = _extract_unit(after_label, label)
            break
    
    # Find value blocks to the right of label
    min_x = label_block.x1
    value_text = _find_value_at_column(row, col_idx, min_x)
    
    if value_text is None:
        return None, unit, "merged"
    
    # Handle FULL_TEXT_FIELDS
    from .field_extractor import FULL_TEXT_FIELDS
    if field_name in FULL_TEXT_FIELDS:
        all_text = " ".join(b.text for b in row.blocks_by_x if b.x0 >= min_x)
        return all_text.strip() if all_text.strip() else None, unit, "multi"
    
    # For single values, try to split by spaces
    if " " in value_text:
        values = value_text.split()
        if col_idx < len(values):
            return values[col_idx], unit, "multi"
        return None, unit, "merged"
    
    # Single value - check if it's shared across columns
    has_multiple_columns = any(
        b.text.strip() and not b.text.startswith("(")
        for b in row.blocks_by_x
        if b.x0 > min_x + 50
    )
    
    if has_multiple_columns:
        return value_text, unit, "multi"
    else:
        return value_text, unit, "shared"


def extract_fields_spatial(
    doc_id: str,
    page_num: int,
    col_idx: int,
    field_labels: dict[str, list[str]],
) -> tuple[dict[str, ExtractedValue], list[str], list[str]]:
    """Extract fields using spatial coordinates."""
    # Try pdfplumber words first (more precise)
    blocks = load_pdfplumber_words(doc_id, page_num)
    
    # Fallback to OCR evidence blocks
    if not blocks:
        blocks = load_evidence_blocks(doc_id, page_num)
    
    rows = _cluster_blocks_into_rows(blocks)
    
    fields = {}
    merged = []
    missing = []
    
    for field_name, labels in field_labels.items():
        extracted = False
        for label in labels:
            result = find_row_value_spatial(rows, label, col_idx, field_name)
            if result is None:
                continue
            
            value, unit, extract_type = result
            
            if extract_type == "merged":
                merged.append(field_name)
                fields[field_name] = ExtractedValue(
                    field_name=field_name,
                    value=None,
                    unit=unit,
                    confidence=0.5,
                    source="merged",
                    notes="Value appears to be shared or merged",
                )
                extracted = True
                break
            
            if extract_type == "missing" or value is None:
                continue
            
            confidence = 0.95 if extract_type == "multi" else 0.85
            fields[field_name] = ExtractedValue(
                field_name=field_name,
                value=value,
                unit=unit,
                confidence=confidence,
                source="spatial",
            )
            extracted = True
            break
        
        if not extracted:
            missing.append(field_name)
            fields[field_name] = ExtractedValue(
                field_name=field_name,
                value=None,
                confidence=0.0,
                source="missing",
                notes="Not found via spatial extraction",
            )
    
    return fields, merged, missing


def extract_from_spatial(
    doc_id: str,
    model_match: ModelMatch,
    pages: list[int] = None,
) -> ExtractionResult:
    """Extract fields using spatial coordinates from evidence blocks."""
    if pages is None:
        pages = [2]
    
    result = ExtractionResult(
        document_id=doc_id,
        model_match=model_match,
        column_index=0,
    )
    
    # Get column index from model finder
    models_found = model_match.all_models_found if hasattr(model_match, 'all_models_found') else []
    result.models_found = models_found
    
    if models_found and model_match.matched_model:
        from .field_extractor import find_column_index
        col_idx = find_column_index(models_found, model_match.matched_model)
        result.column_index = col_idx
    
    # Extract from each page
    all_fields = {}
    all_merged = []
    all_missing = []
    
    for page_num in pages:
        fields, merged, missing = extract_fields_spatial(
            doc_id, page_num, result.column_index, FIELD_TO_ROW_LABEL
        )
        
        all_fields.update(fields)
        all_merged.extend(merged)
        all_missing.extend(missing)
    
    # Remove duplicates
    result.merged_fields = list(set(all_merged))
    result.missing_fields = [f for f in list(set(all_missing)) if f not in all_fields]
    
    # For fields not found spatially, fall back to text extraction
    from .field_extractor import extract_from_cached
    fallback_result = extract_from_cached(doc_id, model_match, pages, use_llm_fallback=False)
    
    # Merge results - prefer spatial over text
    for field_name, val in fallback_result.fields.items():
        if field_name not in all_fields or all_fields[field_name].source == "missing":
            all_fields[field_name] = val
    
    result.fields = all_fields
    
    return result


def print_spatial_result(result: ExtractionResult):
    """Print spatial extraction results."""
    print(f"\nSpatial Extraction Results:")
    print(f"  Document: {result.document_id}")
    print(f"  Target: {result.model_match.matched_model}")
    print(f"  Column index: {result.column_index}")
    
    spatial = {k: v for k, v in result.fields.items() if v.source == "spatial"}
    table = {k: v for k, v in result.fields.items() if v.source == "table"}
    llm = {k: v for k, v in result.fields.items() if v.source == "llm"}
    merged = {k: v for k, v in result.fields.items() if v.source == "merged"}
    missing = {k: v for k, v in result.fields.items() if v.source in ("missing", "llm_error")}
    
    print(f"\n  Spatial extraction ({len(spatial)}):")
    for field_name, val in sorted(spatial.items()):
        unit_str = f" {val.unit}" if val.unit else ""
        print(f"    {field_name}: {val.value}{unit_str}")
    
    if table:
        print(f"\n  Text extraction ({len(table)}):")
        for field_name, val in sorted(table.items()):
            unit_str = f" {val.unit}" if val.unit else ""
            print(f"    {field_name}: {val.value}{unit_str}")
    
    if llm:
        print(f"\n  LLM extraction ({len(llm)}):")
        for field_name, val in sorted(llm.items()):
            print(f"    {field_name}: {val.value}")
    
    if merged:
        print(f"\n  Merged ({len(merged)}):")
        for field_name, val in sorted(merged.items()):
            print(f"    {field_name}: {val.notes}")
    
    if missing:
        print(f"\n  Missing ({len(missing)}):")
        for field_name in sorted(missing):
            print(f"    {field_name}")
