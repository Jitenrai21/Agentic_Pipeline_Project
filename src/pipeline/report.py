from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schemas import IMPORT_CHECKLIST, TASK1_FIELDS
from .reconciliation import ReconciliationResult


def generate_json_report(
    reconciliation: ReconciliationResult,
    extraction_a: dict,
    extraction_b: dict,
    variant_a: str = "",
    variant_b: str = "",
    output_path: Optional[Path] = None,
) -> dict:
    """Generate machine-readable JSON report."""
    
    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "task": "task1_nepal",
            "requested_model": "SUN-5K-G06P3",
            "sources": {
                "source_1": {"variant": variant_a, "extracted_fields": len(extraction_a)},
                "source_2": {"variant": variant_b, "extracted_fields": len(extraction_b)},
            },
        },
        "summary": {
            "total_fields": len(TASK1_FIELDS),
            "agreements": len(reconciliation.agreements),
            "conflicts": len(reconciliation.conflicts),
            "source_only": len(reconciliation.source_only),
            "missing": len(reconciliation.missing),
            "llm_calls": reconciliation.llm_calls_made,
        },
        "checklist_coverage": {},
        "fields": {},
        "conflicts": [],
    }
    
    # Add field details
    for field_name in TASK1_FIELDS:
        rec = reconciliation.fields.get(field_name)
        if rec:
            report["fields"][field_name] = {
                "status": rec.status,
                "value_a": rec.value_a,
                "value_b": rec.value_b,
                "variant_a": rec.variant_a,
                "variant_b": rec.variant_b,
                "confidence": rec.confidence,
                "notes": rec.notes,
            }
    
    # Add conflicts list
    for field_name in reconciliation.conflicts:
        rec = reconciliation.fields.get(field_name)
        if rec:
            report["conflicts"].append({
                "field": field_name,
                "value_a": rec.value_a,
                "value_b": rec.value_b,
                "variant_a": rec.variant_a,
                "variant_b": rec.variant_b,
                "notes": rec.notes,
            })
    
    # Checklist coverage
    for category, fields in IMPORT_CHECKLIST.items():
        covered = [f for f in fields if f in report["fields"]]
        report["checklist_coverage"][category] = {
            "total": len(fields),
            "extracted": len(covered),
            "fields": covered,
        }
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    
    return report


def generate_markdown_report(
    reconciliation: ReconciliationResult,
    extraction_a: dict,
    extraction_b: dict,
    variant_a: str = "",
    variant_b: str = "",
    output_path: Optional[Path] = None,
) -> str:
    """Generate human-readable Markdown import draft."""
    
    lines = []
    lines.append("# Import Review Draft")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Target Model:** SUN-5K-G06P3")
    lines.append(f"**Task:** Nepal Import (China → Nepal)")
    lines.append("")
    
    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Fields | {len(TASK1_FIELDS)} |")
    lines.append(f"| Agreements | {len(reconciliation.agreements)} |")
    lines.append(f"| Conflicts | {len(reconciliation.conflicts)} |")
    lines.append(f"| Source Only | {len(reconciliation.source_only)} |")
    lines.append(f"| Missing | {len(reconciliation.missing)} |")
    lines.append("")
    
    # Source comparison
    lines.append("## Source Comparison")
    lines.append("")
    lines.append(f"| Source | Variant | Fields Extracted |")
    lines.append(f"|--------|---------|------------------|")
    lines.append(f"| Source 1 | {variant_a} | {len(extraction_a)} |")
    lines.append(f"| Source 2 | {variant_b} | {len(extraction_b)} |")
    lines.append("")
    
    # Agreements
    if reconciliation.agreements:
        lines.append("## Verified Fields (Agreement)")
        lines.append("")
        lines.append("These fields match across both sources:")
        lines.append("")
        for field_name in reconciliation.agreements:
            rec = reconciliation.fields[field_name]
            lines.append(f"- **{field_name}**: {rec.value_a}")
        lines.append("")
    
    # Conflicts
    if reconciliation.conflicts:
        lines.append("## Conflicts (Requires Review)")
        lines.append("")
        lines.append("**These fields differ between sources. Manual review required.**")
        lines.append("")
        for field_name in reconciliation.conflicts:
            rec = reconciliation.fields[field_name]
            lines.append(f"### {field_name}")
            lines.append(f"- **{variant_a}:** {rec.value_a}")
            lines.append(f"- **{variant_b}:** {rec.value_b}")
            lines.append(f"- **Reason:** {rec.notes}")
            lines.append("")
    
    # Source only
    if reconciliation.source_only:
        lines.append("## Source-Only Fields")
        lines.append("")
        lines.append("These fields were found in only one source:")
        lines.append("")
        for field_name in reconciliation.source_only:
            rec = reconciliation.fields[field_name]
            value = rec.value_a or rec.value_b
            variant = rec.variant_a or rec.variant_b
            lines.append(f"- **{field_name}**: {value} (from {variant})")
        lines.append("")
    
    # Missing
    if reconciliation.missing:
        lines.append("## Missing Fields")
        lines.append("")
        lines.append("These fields were not found in either source:")
        lines.append("")
        for field_name in reconciliation.missing:
            lines.append(f"- {field_name}")
        lines.append("")
    
    # Checklist
    lines.append("## Import Checklist Coverage")
    lines.append("")
    for category, fields in IMPORT_CHECKLIST.items():
        covered = [f for f in fields if f in reconciliation.fields]
        status = "COMPLETE" if len(covered) == len(fields) else "PARTIAL"
        lines.append(f"### {category.replace('_', ' ').title()} [{status}]")
        lines.append(f"- Extracted: {len(covered)}/{len(fields)}")
        for f in covered:
            lines.append(f"  - {f}")
        lines.append("")
    
    # Notes
    lines.append("## Notes")
    lines.append("")
    lines.append("- Values are presented as-is from source documents")
    lines.append("- Conflicts require manual verification before import")
    lines.append("- Source-only fields may indicate document differences")
    lines.append("")
    
    content = "\n".join(lines)
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    
    return content
