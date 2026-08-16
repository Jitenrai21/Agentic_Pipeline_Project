"""Dump the extracted evidence records for both sources to outputs/evidence_*.json.

The sys.path bootstrap makes `src.pipeline` importable regardless of the
current working directory (adds the repo root = parent of tests/).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.evidence import to_evidence
from src.pipeline.extractor import extract

DOCS = Path("docs")
OUT = Path("outputs")
TARGET = "SUN-5K-G06P3"

SOURCES = [
    ("am2_p1", "datasheet_sun-4-12k-g06p3-eu-am2-p1_231007_en.pdf"),
    ("am2", "datasheet_sun-4-15k-g06p3-eu-am2_240318_en.pdf"),
]

OUT.mkdir(exist_ok=True)
for sid, fname in SOURCES:
    doc = extract(DOCS / fname, sid, TARGET)
    records = to_evidence(doc, TARGET)
    payload = {
        "target_model": TARGET,
        "source_id": sid,
        "page": doc.page,
        "columns": doc.columns,
        "notes": doc.notes,
        "evidence": [r.model_dump() for r in records],
    }
    path = OUT / f"evidence_{sid}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path} ({len(records)} evidence records)")