from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .evidence_layer import EvidenceBlock, BlockType, BBox
from .ingestion import PageData


@dataclass
class VerificationResult:
    """Result of comparing two extraction methods for a single field/block."""
    text_pdfplumber: str
    text_ocr: str
    similarity: float  # 0.0 to 1.0
    match: bool  # True if above threshold
    note: str = ""


@dataclass
class PageVerification:
    """Verification summary for a single page."""
    page_number: int
    method_a: str  # "pdfplumber"
    method_b: str  # "tesseract"
    text_block_count_a: int
    text_block_count_b: int
    table_count_a: int
    table_count_b: int
    text_matches: list[VerificationResult] = field(default_factory=list)
    overall_similarity: float = 0.0
    recommendation: str = ""


@dataclass
class DocumentVerification:
    """Full verification report for a document."""
    document_id: str
    pages: list[PageVerification] = field(default_factory=list)
    overall_score: float = 0.0
    recommended_method: str = ""


#  Text similarity helpers 

def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    import re
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,;:/%-]", "", text)
    return text


def _text_similarity(a: str, b: str) -> float:
    """Compute character-level similarity between two strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)

    if a_norm == b_norm:
        return 1.0

    # Simple character overlap ratio
    set_a = set(a_norm)
    set_b = set(b_norm)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _token_similarity(a: str, b: str) -> float:
    """Compute token-level similarity using word overlap."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    tokens_a = set(_normalize_text(a).split())
    tokens_b = set(_normalize_text(b).split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) if union else 0.0


# ── Block matching ─────────────────────────────────────────────────

def _match_blocks_by_text(
    blocks_a: list[EvidenceBlock],
    blocks_b: list[EvidenceBlock],
) -> list[tuple[EvidenceBlock, EvidenceBlock]]:
    """Match blocks from two methods by text content similarity."""
    matches = []
    used_b = set()

    for block_a in blocks_a:
        if block_a.block_type != BlockType.TEXT:
            continue

        best_match = None
        best_score = 0.0

        for j, block_b in enumerate(blocks_b):
            if j in used_b:
                continue
            if block_b.block_type != BlockType.TEXT:
                continue

            sim = _token_similarity(block_a.text, block_b.text)
            if sim > best_score:
                best_score = sim
                best_match = (j, block_b)

        if best_match and best_score > 0.2:
            idx, block_b = best_match
            used_b.add(idx)
            matches.append((block_a, block_b))

    return matches


# ── Page-level verification ────────────────────────────────────────

def verify_page(
    page_number: int,
    blocks_a: list[EvidenceBlock],
    blocks_b: list[EvidenceBlock],
    method_a: str = "pdfplumber",
    method_b: str = "tesseract",
) -> PageVerification:
    """Verify extraction quality by comparing two methods on same page."""
    text_a = [b for b in blocks_a if b.block_type == BlockType.TEXT]
    text_b = [b for b in blocks_b if b.block_type == BlockType.TEXT]
    tables_a = [b for b in blocks_a if b.block_type == BlockType.TABLE]
    tables_b = [b for b in blocks_b if b.block_type == BlockType.TABLE]

    matched = _match_blocks_by_text(text_a, text_b)
    results = []
    for block_a, block_b in matched:
        sim = _token_similarity(block_a.text, block_b.text)
        results.append(VerificationResult(
            text_pdfplumber=block_a.text[:100],
            text_ocr=block_b.text[:100],
            similarity=sim,
            match=sim > 0.5,
        ))

    avg_sim = (
        sum(r.similarity for r in results) / len(results) if results else 0.0
    )

    if avg_sim > 0.7:
        rec = f"Both methods agree well (similarity={avg_sim:.2f}). Use pdfplumber (faster)."
    elif avg_sim > 0.4:
        rec = f"Partial agreement (similarity={avg_sim:.2f}). Cross-check critical values."
    else:
        rec = f"Low agreement (similarity={avg_sim:.2f}). Manual review recommended."

    return PageVerification(
        page_number=page_number,
        method_a=method_a,
        method_b=method_b,
        text_block_count_a=len(text_a),
        text_block_count_b=len(text_b),
        table_count_a=len(tables_a),
        table_count_b=len(tables_b),
        text_matches=results,
        overall_similarity=avg_sim,
        recommendation=rec,
    )


# ── Document-level verification ────────────────────────────────────

def verify_document(
    document_id: str,
    blocks_a: dict[int, list[EvidenceBlock]],
    blocks_b: dict[int, list[EvidenceBlock]],
    method_a: str = "pdfplumber",
    method_b: str = "tesseract",
) -> DocumentVerification:
    """Verify extraction across all pages of a document."""
    pages = []
    all_sims = []

    for page_num in sorted(set(blocks_a.keys()) & set(blocks_b.keys())):
        pv = verify_page(
            page_number=page_num,
            blocks_a=blocks_a[page_num],
            blocks_b=blocks_b[page_num],
            method_a=method_a,
            method_b=method_b,
        )
        pages.append(pv)
        all_sims.append(pv.overall_similarity)

    overall = sum(all_sims) / len(all_sims) if all_sims else 0.0

    if overall > 0.7:
        rec = "pdfplumber"
    elif overall > 0.4:
        rec = "pdfplumber (with OCR cross-check)"
    else:
        rec = "manual review needed"

    return DocumentVerification(
        document_id=document_id,
        pages=pages,
        overall_score=overall,
        recommended_method=rec,
    )
