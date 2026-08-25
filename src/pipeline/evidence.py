from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import CACHE_DIR
from .ingestion import PageData, ExtractedTable
from .evidence_layer import EvidenceBlock, BlockType, BBox, TableBoundary, CellInfo


def _serialize(obj):
    """Handle dataclass and Path serialization for JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


#  PageData storage (legacy) 

def store_page_data(
    document_id: str,
    page_number: int,
    page_data: PageData,
) -> Path:
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
    paths = []
    for page in pages:
        p = store_page_data(document_id, page.page_number, page)
        paths.append(p)
        print(f"  Stored page {page.page_number}: {p.name} "
              f"({page.extraction_method}, conf={page.confidence:.2f})")
    return paths


def load_page_data(document_id: str, page_number: int) -> PageData:
    path = CACHE_DIR / document_id / "pages" / f"page_{page_number}.json"
    raw = json.loads(path.read_text())
    tables = [ExtractedTable(**t) for t in raw.get("tables", [])]
    return PageData(
        page_number=raw["page_number"],
        raw_text=raw["raw_text"],
        tables=tables,
        words=raw.get("words", []),
        extraction_method=raw.get("extraction_method", "text"),
        confidence=raw.get("confidence", 0.0),
    )


def load_all_pages(document_id: str) -> list[PageData]:
    pages_dir = CACHE_DIR / document_id / "pages"
    if not pages_dir.exists():
        return []
    page_files = sorted(pages_dir.glob("page_*.json"))
    pages = []
    for pf in page_files:
        page_num = int(pf.stem.split("_")[1])
        pages.append(load_page_data(document_id, page_num))
    return pages


#  EvidenceBlock storage 

def _block_to_dict(block: EvidenceBlock) -> dict:
    return block.to_dict()


def _dict_to_block(d: dict) -> EvidenceBlock:
    bbox_data = d.get("bbox")
    if bbox_data and isinstance(bbox_data, list):
        bbox = BBox(x0=bbox_data[0], y0=bbox_data[1], x1=bbox_data[2], y1=bbox_data[3])
    elif bbox_data and isinstance(bbox_data, dict):
        bbox = BBox(**bbox_data)
    else:
        bbox = None

    table = None
    if d.get("table"):
        t = d["table"]
        cells = []
        for c in t.get("cells", []):
            cb = c.get("bbox")
            if cb and isinstance(cb, list):
                cell_bbox = BBox(x0=cb[0], y0=cb[1], x1=cb[2], y1=cb[3])
            elif cb and isinstance(cb, dict):
                cell_bbox = BBox(**cb)
            else:
                cell_bbox = None
            cells.append(CellInfo(
                text=c["text"],
                row_idx=c["row_idx"],
                col_idx=c["col_idx"],
                bbox=cell_bbox,
            ))

        tb = t.get("bbox")
        if tb and isinstance(tb, list):
            table_bbox = BBox(x0=tb[0], y0=tb[1], x1=tb[2], y1=tb[3])
        elif tb and isinstance(tb, dict):
            table_bbox = BBox(**tb)
        else:
            table_bbox = None

        table = TableBoundary(
            table_id=t["table_id"],
            headers=t["headers"],
            rows=t["rows"],
            cells=cells,
            bbox=table_bbox,
            num_rows=t.get("num_rows", 0),
            num_cols=t.get("num_cols", 0),
        )
    return EvidenceBlock(
        document_id=d["document_id"],
        page=d["page"],
        block_type=BlockType(d["block_type"]),
        text=d["text"],
        bbox=bbox,
        extraction_method=d.get("extraction_method", "pdfplumber"),
        confidence=d.get("confidence", 1.0),
        table=table,
    )


def store_evidence_blocks(
    document_id: str,
    page_number: int,
    blocks: list[EvidenceBlock],
) -> Path:
    """Persist evidence blocks for a single page."""
    store_dir = CACHE_DIR / document_id / "evidence"
    store_dir.mkdir(parents=True, exist_ok=True)
    out_path = store_dir / f"page_{page_number}.json"
    data = [_block_to_dict(b) for b in blocks]
    out_path.write_text(json.dumps(data, indent=2))
    return out_path


def store_all_evidence(
    document_id: str,
    all_blocks: dict[int, list[EvidenceBlock]],
) -> list[Path]:
    """Store evidence blocks for all pages. Returns list of written paths."""
    paths = []
    for page_num in sorted(all_blocks.keys()):
        blocks = all_blocks[page_num]
        p = store_evidence_blocks(document_id, page_num, blocks)
        paths.append(p)
        table_count = sum(1 for b in blocks if b.block_type == BlockType.TABLE)
        text_count = sum(1 for b in blocks if b.block_type == BlockType.TEXT)
        print(f"  Evidence page {page_num}: {text_count} text blocks, "
              f"{table_count} tables -> {p.name}")
    return paths


def load_evidence_blocks(
    document_id: str,
    page_number: int,
) -> list[EvidenceBlock]:
    """Load evidence blocks for a single page."""
    path = CACHE_DIR / document_id / "evidence" / f"page_{page_number}.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return [_dict_to_block(d) for d in raw]


def load_all_evidence(
    document_id: str,
) -> dict[int, list[EvidenceBlock]]:
    """Load all evidence blocks for a document."""
    evidence_dir = CACHE_DIR / document_id / "evidence"
    if not evidence_dir.exists():
        return {}
    result = {}
    for pf in sorted(evidence_dir.glob("page_*.json")):
        page_num = int(pf.stem.split("_")[1])
        result[page_num] = load_evidence_blocks(document_id, page_num)
    return result


def print_evidence_summary(document_id: str):
    """Print a summary of all evidence blocks for a document."""
    all_blocks = load_all_evidence(document_id)
    print(f"\n=== Evidence Summary: {document_id} ===")
    for page_num in sorted(all_blocks.keys()):
        blocks = all_blocks[page_num]
        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        texts = [b for b in blocks if b.block_type == BlockType.TEXT]
        print(f"\n  Page {page_num}:")
        print(f"    Text blocks: {len(texts)}")
        for t in texts:
            preview = t.text[:80].replace("\n", " ").encode("ascii", "replace").decode()
            print(f"      [{t.extraction_method}] {preview}...")
        print(f"    Tables: {len(tables)}")
        for t in tables:
            if t.table:
                print(f"      [{t.extraction_method}] {t.table.table_id}: "
                      f"{t.table.num_rows} rows x {t.table.num_cols} cols")
                if t.table.rows:
                    sample = [str(c)[:20] for c in t.table.rows[0]]
                    print(f"        Sample: {sample}")
