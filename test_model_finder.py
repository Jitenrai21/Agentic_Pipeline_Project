"""Test Phase 4: find_target_model using LLM."""
from pathlib import Path

import pdfplumber

from src.pipeline.config import SOURCES
from src.pipeline.fetcher import fetch_documents
from src.pipeline.evidence_layer import extract_evidence_from_page
from src.pipeline.model_finder import find_target_model, find_target_model_all_sources


def main():
    print("Phase 4: find_target_model")

    print("\n[1/3] Fetching documents...")
    docs = fetch_documents()

    print("\n[2/3] Building evidence blocks...")
    all_sources = {}
    for doc_id, meta in docs.items():
        pdf_path = Path(meta["local_path"])
        blocks = {}
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                blocks[page_num] = extract_evidence_from_page(
                    document_id=doc_id,
                    page_number=page_num,
                    page=page,
                )
        all_sources[doc_id] = blocks
        print(f"  {doc_id}: {sum(len(b) for b in blocks.values())} blocks")

    requested_model = "SUN-5K-G06P3"

    print(f"\n[3/3] Finding target model: {requested_model}")

    results = find_target_model_all_sources(requested_model, all_sources)

    for match in results:
        print(f"\nSource: {match.source_document}")
        print(f"  Requested: {match.requested}")
        print(f"  Matched: {match.matched_model}")
        print(f"  Variant: {match.variant}")
        print(f"  Confidence: {match.confidence:.2f}")
        print(f"  Notes: {match.notes}")


if __name__ == "__main__":
    main()
