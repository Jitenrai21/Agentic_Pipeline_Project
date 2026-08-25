from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import CACHE_DIR
from .ingestion import PageData, ExtractedTable


def _serialize(obj):
    """Handle dataclass and Path serialization for JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


def store_page_data(
    document_id: str,
    page_number: int,
    page_data: PageData,
) -> Path:
    """
    Persist extracted page data to the evidence store.
    Returns path to written JSON file.
    """
    store_dir = CACHE_DIR / document_id / "pages"
    store_dir.mkdir(parents=True, exist_ok=True)

    out_path = store_dir / f"page_{page_number}.json"
    data = asdict(page_data)
    out_path.write_text(json.dumps(data, indent=2, default=_serialize))

    return out_path


def store_all_pages(
    document_id: str,
    pages: list[PageData],
) -> list[Path]:
    """Store all pages for a document. Returns list of written paths."""
    paths = []
    for page in pages:
        p = store_page_data(document_id, page.page_number, page)
        paths.append(p)
        print(f"  Stored page {page.page_number}: {p.name} "
              f"({page.extraction_method}, conf={page.confidence:.2f})")
    return paths


def load_page_data(document_id: str, page_number: int) -> PageData:
    """Load previously stored page data."""
    path = CACHE_DIR / document_id / "pages" / f"page_{page_number}.json"
    raw = json.loads(path.read_text())
    tables = [
        ExtractedTable(**t) for t in raw.get("tables", [])
    ]
    return PageData(
        page_number=raw["page_number"],
        raw_text=raw["raw_text"],
        tables=tables,
        words=raw.get("words", []),
        extraction_method=raw.get("extraction_method", "text"),
        confidence=raw.get("confidence", 0.0),
    )


def load_all_pages(document_id: str) -> list[PageData]:
    """Load all stored pages for a document, sorted by page number."""
    pages_dir = CACHE_DIR / document_id / "pages"
    if not pages_dir.exists():
        return []

    page_files = sorted(pages_dir.glob("page_*.json"))
    pages = []
    for pf in page_files:
        page_num = int(pf.stem.split("_")[1])
        pages.append(load_page_data(document_id, page_num))
    return pages
