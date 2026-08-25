from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import CACHE_DIR, OUTPUT_DIR
from .evidence_layer import EvidenceBlock, BlockType, TableBoundary
from .evidence import load_all_evidence
from .verification import DocumentVerification


def _format_bbox(bbox) -> str:
    if not bbox:
        return "N/A"
    return f"({bbox.x0:.0f}, {bbox.y0:.0f}, {bbox.x1:.0f}, {bbox.y1:.0f})"


def generate_evidence_report(
    document_id: str,
    blocks: dict[int, list[EvidenceBlock]],
    verification: DocumentVerification | None = None,
) -> str:
    """Generate a Markdown evidence report for a document."""
    lines = []
    lines.append(f"# Evidence Report: {document_id}")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("")

    # Summary stats
    total_text = sum(
        1 for page in blocks.values()
        for b in page if b.block_type == BlockType.TEXT
    )
    total_tables = sum(
        1 for page in blocks.values()
        for b in page if b.block_type == BlockType.TABLE
    )
    methods = set(
        b.extraction_method
        for page in blocks.values()
        for b in page
    )
    avg_conf = 0.0
    conf_count = 0
    for page in blocks.values():
        for b in page:
            if b.confidence > 0:
                avg_conf += b.confidence
                conf_count += 1
    avg_conf = avg_conf / conf_count if conf_count > 0 else 0.0

    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Total pages | {len(blocks)} |")
    lines.append(f"| Text blocks | {total_text} |")
    lines.append(f"| Table blocks | {total_tables} |")
    lines.append(f"| Extraction methods | {', '.join(methods)} |")
    lines.append(f"| Average confidence | {avg_conf:.2f} |")
    lines.append("")

    # Verification results
    if verification:
        lines.append("## Verification Results")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Overall similarity | {verification.overall_score:.2f} |")
        lines.append(f"| Recommended method | {verification.recommended_method} |")
        lines.append("")

        for pv in verification.pages:
            lines.append(f"### Page {pv.page_number}")
            lines.append("")
            lines.append(f"- pdfplumber blocks: {pv.text_block_count_a} text, {pv.table_count_a} tables")
            lines.append(f"- tesseract blocks: {pv.text_block_count_b} text, {pv.table_count_b} tables")
            lines.append(f"- Similarity: {pv.overall_similarity:.2f}")
            lines.append(f"- Recommendation: {pv.recommendation}")
            lines.append("")

    # Page details
    lines.append("## Page Details")
    lines.append("")

    for page_num in sorted(blocks.keys()):
        page_blocks = blocks[page_num]
        text_blocks = [b for b in page_blocks if b.block_type == BlockType.TEXT]
        table_blocks = [b for b in page_blocks if b.block_type == BlockType.TABLE]

        lines.append(f"### Page {page_num}")
        lines.append("")

        if text_blocks:
            lines.append(f"**Text Blocks ({len(text_blocks)}):**")
            lines.append("")
            for i, b in enumerate(text_blocks[:10], 1):
                preview = b.text[:80].replace("\n", " ")
                lines.append(f"{i}. `[{b.extraction_method}]` {preview}...")
                lines.append(f"   - BBox: {_format_bbox(b.bbox)}")
                lines.append(f"   - Confidence: {b.confidence:.2f}")
            if len(text_blocks) > 10:
                lines.append(f"\n   ... and {len(text_blocks) - 10} more text blocks")
            lines.append("")

        if table_blocks:
            lines.append(f"**Tables ({len(table_blocks)}):**")
            lines.append("")
            for b in table_blocks:
                if b.table:
                    lines.append(f"- `{b.table.table_id}`: {b.table.num_rows} rows x {b.table.num_cols} cols")
                    lines.append(f"  - BBox: {_format_bbox(b.bbox)}")
                    if b.table.headers:
                        lines.append(f"  - Headers: {b.table.headers[:5]}...")
                    if b.table.rows:
                        lines.append(f"  - Sample row: {b.table.rows[0][:5]}...")
            lines.append("")

    # Raw evidence data (JSON)
    lines.append("## Raw Evidence Data")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Click to expand JSON</summary>")
    lines.append("")
    lines.append("```json")

    evidence_dict = {}
    for page_num, page_blocks in blocks.items():
        evidence_dict[f"page_{page_num}"] = [b.to_dict() for b in page_blocks]

    lines.append(json.dumps(evidence_dict, indent=2)[:5000])
    if len(json.dumps(evidence_dict)) > 5000:
        lines.append("\n... (truncated)")
    lines.append("```")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)


def save_report(document_id: str, report: str) -> Path:
    """Save report to outputs directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"evidence_report_{document_id}.md"
    out_path.write_text(report, encoding="utf-8")
    return out_path


def generate_comparison_report(
    document_id: str,
    blocks_pdfplumber: dict[int, list[EvidenceBlock]],
    blocks_ocr: dict[int, list[EvidenceBlock]],
) -> str:
    """Generate a comparison report between pdfplumber and OCR extraction."""
    from .verification import verify_document

    verification = verify_document(
        document_id=document_id,
        blocks_a=blocks_pdfplumber,
        blocks_b=blocks_ocr,
        method_a="pdfplumber",
        method_b="tesseract",
    )

    return generate_evidence_report(
        document_id=document_id,
        blocks=blocks_pdfplumber,
        verification=verification,
    )
