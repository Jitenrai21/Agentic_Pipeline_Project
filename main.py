"""
Agentic Pipeline — Document Ingestion Layer
Entry point for testing fetch + parse + evidence storage.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.config import SOURCES, CACHE_DIR
from src.pipeline.fetcher import fetch_documents
from src.pipeline.ingestion import ingest_document, PageData
from src.pipeline.evidence import store_all_pages, load_all_pages


def run_ingestion():
    print("Phase 2: Document Ingestion Layer")

    # Step 1: Fetch documents
    print("\n[1/3] Fetching source documents...")
    docs = fetch_documents()

    # Step 2: Ingest and parse each document
    print("\n[2/3] Ingesting and parsing...")
    all_results = {}
    for doc_id, meta in docs.items():
        print(f"\n--- {doc_id} ({meta['variant']}) ---")
        pdf_path = Path(meta["local_path"])
        pages = ingest_document(pdf_path)

        # Step 3: Store in evidence store
        print(f"\n[3/3] Storing evidence for {doc_id}...")
        store_all_pages(doc_id, pages)

        all_results[doc_id] = pages

    # Print summary
    print("Ingestion Summary")
    for doc_id, pages in all_results.items():
        total_tables = sum(len(p.tables) for p in pages)
        methods = set(p.extraction_method for p in pages)
        avg_conf = (
            sum(p.confidence for p in pages) / len(pages) if pages else 0
        )
        print(f"\n{doc_id}:")
        print(f"  Pages: {len(pages)}")
        print(f"  Tables found: {total_tables}")
        print(f"  Extraction methods: {methods}")
        print(f"  Avg confidence: {avg_conf:.2f}")

    return all_results


if __name__ == "__main__":
    run_ingestion()
