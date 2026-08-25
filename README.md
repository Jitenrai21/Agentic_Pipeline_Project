# Agentic Pipeline

An AI-powered document extraction pipeline for analyzing solar inverter datasheets and generating import review reports.

## Overview

This pipeline extracts technical specifications from conflicting manufacturer datasheets, reconciles differences, and produces structured output for import review.

**Target:** Deye SUN-5K-G06P3 solar inverter (5 kW)  
**Task:** Nepal import (China → Nepal)  
**Sources:** Two conflicting Deye datasheets (AM2 and AM2-P1 variants)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LANGGRAPH PIPELINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  fetcher    │    │  ingestion  │    │  evidence   │    │  schemas    │  │
│  │             │    │             │    │  _layer     │    │             │  │
│  │ - PDFs      │───▶│ - pdfplumber│───▶│ - Text      │───▶│ - Models    │  │
│  │ - Metadata  │    │ - OCR       │    │ - Tables    │    │ - Fields    │  │
│  │ - URLs      │    │ - Fallback  │    │ - BBox      │    │ - Status    │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│         │                  │                  │                  │           │
│         ▼                  ▼                  ▼                  ▼           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        EXTRACTION LAYER                             │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │   │
│  │  │  model      │    │  field      │    │  llm        │             │   │
│  │  │  _finder    │    │  _extractor │    │  _client    │             │   │
│  │  │             │    │             │    │             │             │   │
│  │  │ - LLM       │───▶│ - Rules     │───▶│ - OpenRouter│             │   │
│  │  │ - Match     │    │ - Patterns  │    │ - API       │             │   │
│  │  │ - Variant   │    │ - Fallback  │    │ - Cleanup   │             │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                  │                  │                             │
│         ▼                  ▼                  ▼                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      RECONCILIATION LAYER                           │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │   │
│  │  │  reconcil   │    │  report     │    │  verify     │             │   │
│  │  │  -iation    │    │             │    │             │             │   │
│  │  │             │───▶│ - JSON      │───▶│ - Validate  │             │   │
│  │  │ - Compare   │    │ - Markdown  │    │ - Verify    │             │   │
│  │  │ - Conflict  │    │ - Draft     │    │ - Check     │             │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│                           ┌─────────────┐                                  │
│                           │    END      │                                  │
│                           └─────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Flow

| Step | Node | Module | Purpose |
|------|------|--------|---------|
| 1 | `fetch` | `fetcher.py` | Download PDFs, store metadata |
| 2 | `extract_1` | `field_extractor.py` | Extract from Source 1 (AM2-P1) |
| 3 | `extract_2` | `field_extractor.py` | Extract from Source 2 (AM2) |
| 4 | `reconcile` | `reconciliation.py` | Compare fields, flag conflicts |
| 5 | `report` | `report.py` | Generate MD + JSON reports |
| 6 | `summary` | — | Print final results |

## Pipeline Components

| Module | Purpose | Key Functions |
|---|---|---|
| `config.py` | Configuration, paths, API keys | `SOURCES`, `CACHE_DIR`, `get_openrouter_api_key()` |
| `fetcher.py` | Downloads PDFs, stores metadata | `fetch_documents()` |
| `ingestion.py` | PDF parsing (pdfplumber) + OCR fallback | `parse_pdf()`, `parse_with_ocr()` |
| `evidence_layer.py` | Text/table extraction with bounding boxes | `extract_evidence_from_page()`, `extract_evidence_from_ocr()` |
| `model_finder.py` | LLM-based model identification | `find_target_model()`, `find_target_model_all_sources()` |
| `field_extractor.py` | Rule-based field extraction + LLM fallback | `extract_from_cached()`, `extract_missing_with_llm()` |
| `reconciliation.py` | Source comparison and conflict detection | `reconcile_fields()`, `_llm_reconcile_batch()` |
| `report.py` | MD + JSON report generation | `generate_json_report()`, `generate_markdown_report()` |
| `schemas.py` | Pydantic data models | `TASK1_FIELDS`, `IMPORT_CHECKLIST`, `ExtractionOutput` |
| `llm_client.py` | OpenRouter API client | `call_llm()`, `call_llm_text()`, `_clean_reasoning_output()` |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API key

Create `.env` file:
```
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
```

### 3. Run the pipeline

```bash
python main.py
```

## Usage

### Full pipeline
```bash
python main.py
```

### Individual modules
```bash
# Fetch documents only
python -c "from src.pipeline.fetcher import fetch_documents; fetch_documents()"

# Extract from single source
python -c "from src.pipeline.field_extractor import extract_from_cached; ..."
```

## Output

### Reports
- `outputs/import_review.json` — Machine-readable JSON
- `outputs/import_draft.md` — Human-readable Markdown

### Example output
```
Reconciliation Results:
  Agreements: 3
  Conflicts: 4
  Source only: 14
  Missing: 7
```

## Extracted Fields

| Category | Fields |
|---|---|
| Product Identity | model, variant, rated_power, max_pv_input_power, etc. |
| Electrical Specs | voltage, current, efficiency, frequency |
| Compliance | grid_standards, safety_emc, surge_protection |
| Protection | dc_reverse_polarity, thermal, islanding |
| Physical | weight, ip_rating, operating_temperature |

## Reconciliation Status

| Status | Meaning |
|---|---|
| `verified` | Both sources agree |
| `conflict` | Sources disagree (requires review) |
| `source_only` | Found in only one source |
| `missing` | Not found in either source |

## Configuration

### Sources
Edit `src/pipeline/config.py` to add/modify source URLs:
```python
SOURCES = {
    "source_1": {"url": "...", "variant": "AM2-P1"},
    "source_2": {"url": "...", "variant": "AM2"},
}
```

### Fields
Edit `src/pipeline/schemas.py` to modify extraction fields:
```python
TASK1_FIELDS = [
    "product.model",
    "product.rated_power",
    ...
]
```

## Project Structure

```
agentic_pipeline_project/
├── main.py                     # LangGraph pipeline entry point
├── requirements.txt            # Python dependencies
├── .env                       # API keys (not in git)
├── src/
│   └── pipeline/
│       ├── __init__.py        # Package init
│       ├── config.py          # Configuration, paths, API keys
│       ├── fetcher.py         # Document download, metadata
│       ├── ingestion.py       # PDF/OCR parsing
│       ├── evidence_layer.py  # Text/table extraction, bboxes
│       ├── model_finder.py    # LLM model identification
│       ├── field_extractor.py # Field extraction (rules + LLM)
│       ├── reconciliation.py  # Source comparison, conflicts
│       ├── report.py          # MD + JSON report generation
│       ├── schemas.py         # Pydantic models, field definitions
│       ├── llm_client.py      # OpenRouter API client
│       └── verification.py    # Verification utilities
├── cache/                     # Cached PDFs and extractions
│   ├── source_1/              # AM2-P1 variant
│   │   ├── *.pdf              # Downloaded PDF
│   │   ├── metadata.json      # Document metadata
│   │   └── pages/             # Extracted page data
│   └── source_2/              # AM2 variant
│       ├── *.pdf              # Downloaded PDF
│       ├── metadata.json      # Document metadata
│       └── pages/             # Extracted page data
└── outputs/                   # Generated reports
    ├── import_review.json     # Machine-readable output
    ├── import_draft.md        # Human-readable draft
    └── ocr_evidence_*.json    # OCR extraction results

```

## Technical Details

### Extraction Strategy
1. **Rule-based extraction** — Fast, free, reliable for most fields
2. **LLM fallback** — Handles edge cases (truncated text, ambiguous values)
3. **Reconciliation** — Compares sources, flags conflicts

### LLM Usage
- **Model:** nvidia/nemotron-3.5-lightning:free (OpenRouter)
- **Usage:** Only for model identification and missing field extraction
- **Token efficiency:** Batched calls, rules-first approach

### OCR Support
- Primary: pdfplumber (text extraction)
- Fallback: Tesseract OCR (for scanned/image PDFs)

## License

Internal project for assessment purposes.