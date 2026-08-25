from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pdfplumber


class BlockType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


@dataclass
class BBox:
    """Bounding box: (x0, y0, x1, y1) in PDF points (72 per inch)."""
    x0: float
    y0: float
    x1: float
    y1: float

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class CellInfo:
    """A single cell in a table."""
    text: str
    row_idx: int
    col_idx: int
    bbox: Optional[BBox] = None


@dataclass
class TableBoundary:
    """Full table structure with cells and boundaries."""
    table_id: str
    headers: list[str]
    rows: list[list[str]]
    cells: list[CellInfo] = field(default_factory=list)
    bbox: Optional[BBox] = None
    num_rows: int = 0
    num_cols: int = 0


@dataclass
class EvidenceBlock:
    """Ground-truth evidence unit from a single source document."""
    document_id: str
    page: int
    block_type: BlockType
    text: str
    bbox: Optional[BBox] = None
    extraction_method: str = "pdfplumber"
    confidence: float = 1.0
    table: Optional[TableBoundary] = None

    def to_dict(self) -> dict:
        d = {
            "document_id": self.document_id,
            "page": self.page,
            "block_type": self.block_type.value,
            "text": self.text,
            "bbox": self.bbox.to_list() if self.bbox else None,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
        }
        if self.table:
            d["table"] = {
                "table_id": self.table.table_id,
                "headers": self.table.headers,
                "rows": self.table.rows,
                "num_rows": self.table.num_rows,
                "num_cols": self.table.num_cols,
                "bbox": self.table.bbox.to_list() if self.table.bbox else None,
                "cells": [
                    {
                        "text": c.text,
                        "row_idx": c.row_idx,
                        "col_idx": c.col_idx,
                        "bbox": c.bbox.to_list() if c.bbox else None,
                    }
                    for c in self.table.cells
                ],
            }
        return d


#  Shared helpers 

def _words_bbox(words: list[dict]) -> Optional[BBox]:
    if not words:
        return None
    x0 = min(w["x0"] for w in words)
    y0 = min(w["y0"] for w in words)
    x1 = max(w["x1"] for w in words)
    y1 = max(w["y1"] for w in words)
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _cluster_words_into_blocks(
    words: list[dict], y_threshold: float = 5.0
) -> list[list[dict]]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["y0"], w["x0"]))
    blocks: list[list[dict]] = []
    current_block: list[dict] = [sorted_words[0]]
    for word in sorted_words[1:]:
        prev = current_block[-1]
        if abs(word["y0"] - prev["y0"]) <= y_threshold:
            current_block.append(word)
        else:
            blocks.append(current_block)
            current_block = [word]
    blocks.append(current_block)
    return blocks


#  pdfplumber extraction 

def _words_to_text_pdfplumber(words: list[dict]) -> str:
    return " ".join(w["text"] for w in words)


def extract_evidence_from_page(
    document_id: str,
    page_number: int,
    page: pdfplumber.page.Page,
    extraction_method: str = "pdfplumber",
) -> list[EvidenceBlock]:
    blocks: list[EvidenceBlock] = []

    table_bboxes: list[BBox] = []
    tables = page.find_tables() or []

    for idx, table in enumerate(tables):
        t_bbox = BBox(
            x0=table.bbox[0], y0=table.bbox[1],
            x1=table.bbox[2], y1=table.bbox[3],
        )
        table_bboxes.append(t_bbox)

        data = table.extract()
        if not data or len(data) < 1:
            continue

        headers = [str(c) if c else "" for c in data[0]]
        rows = []
        cells: list[CellInfo] = []

        for row_idx, row in enumerate(data[1:] or []):
            row_data = [str(c) if c else "" for c in row]
            rows.append(row_data)
            for col_idx, cell_text in enumerate(row_data):
                cell_bbox = None
                if hasattr(table, "cells") and table.cells:
                    flat_idx = row_idx * len(headers) + col_idx
                    if flat_idx < len(table.cells):
                        c = table.cells[flat_idx]
                        cell_bbox = BBox(x0=c[0], y0=c[1], x1=c[2], y1=c[3])
                cells.append(CellInfo(
                    text=cell_text, row_idx=row_idx,
                    col_idx=col_idx, bbox=cell_bbox,
                ))

        table_boundary = TableBoundary(
            table_id=f"table_{idx + 1}", headers=headers, rows=rows,
            cells=cells, bbox=t_bbox,
            num_rows=len(rows), num_cols=len(headers),
        )

        table_text = "\n".join(
            [" | ".join(headers)] + [" | ".join(r) for r in rows]
        )

        blocks.append(EvidenceBlock(
            document_id=document_id, page=page_number,
            block_type=BlockType.TABLE, text=table_text,
            bbox=t_bbox, extraction_method=extraction_method,
            confidence=1.0, table=table_boundary,
        ))

    words = page.extract_words() or []

    def _in_table(word: dict) -> bool:
        for tb in table_bboxes:
            if (word["top"] >= tb.y0 and word["bottom"] <= tb.y1
                    and word["x0"] >= tb.x0 and word["x1"] <= tb.x1):
                return True
        return False

    text_words = [w for w in words if not _in_table(w)]

    pdf_words = []
    for w in text_words:
        pdf_words.append({
            "text": w["text"],
            "x0": w["x0"],
            "y0": w["top"],
            "x1": w["x1"],
            "y1": w["bottom"],
        })

    text_clusters = _cluster_words_into_blocks(pdf_words)

    for cluster in text_clusters:
        text = " ".join(w["text"] for w in cluster)
        bbox = _words_bbox(cluster)
        if text.strip():
            blocks.append(EvidenceBlock(
                document_id=document_id, page=page_number,
                block_type=BlockType.TEXT, text=text,
                bbox=bbox, extraction_method=extraction_method,
                confidence=1.0,
            ))

    blocks.sort(key=lambda b: b.bbox.y0 if b.bbox else 0)
    return blocks


def extract_evidence_from_document(
    document_id: str,
    pdf_path: str,
) -> dict[int, list[EvidenceBlock]]:
    all_blocks: dict[int, list[EvidenceBlock]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            blocks = extract_evidence_from_page(
                document_id=document_id,
                page_number=page_num,
                page=page,
            )
            all_blocks[page_num] = blocks
    return all_blocks


#  OCR extraction 

def extract_evidence_from_ocr(
    document_id: str,
    page_number: int,
    raw_text: str,
    words: list[dict],
    confidence: float = 0.8,
) -> list[EvidenceBlock]:
    """
    Create EvidenceBlocks from OCR output.
    words: list of dicts with keys: text, x0, y0, x1, y1, conf
    """
    blocks: list[EvidenceBlock] = []

    text_clusters = _cluster_words_into_blocks(words)

    for cluster in text_clusters:
        text = " ".join(w["text"] for w in cluster)
        bbox = _words_bbox(cluster)
        avg_conf = sum(w.get("conf", 80) for w in cluster) / len(cluster) / 100.0
        if text.strip():
            blocks.append(EvidenceBlock(
                document_id=document_id, page=page_number,
                block_type=BlockType.TEXT, text=text,
                bbox=bbox, extraction_method="tesseract",
                confidence=avg_conf,
            ))

    blocks.sort(key=lambda b: b.bbox.y0 if b.bbox else 0)
    return blocks
