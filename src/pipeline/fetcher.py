from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pdfplumber

from .config import CACHE_DIR, SOURCES


def _sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _page_count(pdf_path: Path) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def fetch_documents() -> dict[str, dict]:
    """
    Download all source PDFs and store metadata.
    Returns dict keyed by document_id.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    for doc_id, meta in SOURCES.items():
        doc_dir = CACHE_DIR / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        filename = meta["url"].split("/")[-1]
        pdf_path = doc_dir / filename

        # Download if not cached or hash changed
        if not pdf_path.exists():
            print(f"Downloading {doc_id}: {meta['url']}")
            with httpx.Client(follow_redirects=True, timeout=30) as client:
                resp = client.get(meta["url"])
                resp.raise_for_status()
                pdf_path.write_bytes(resp.content)
        else:
            print(f"Using cached {doc_id}: {filename}")

        record = {
            "document_id": doc_id,
            "url": meta["url"],
            "filename": filename,
            "variant": meta.get("variant"),
            "revision_date": meta.get("revision_date"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "sha256": _sha256(pdf_path),
            "page_count": _page_count(pdf_path),
            "local_path": str(pdf_path),
        }

        # Persist metadata
        meta_path = doc_dir / "metadata.json"
        meta_path.write_text(json.dumps(record, indent=2))

        results[doc_id] = record
        print(f"  -> {filename} ({record['page_count']} pages, {record['sha256'][:12]}...)")

    return results
