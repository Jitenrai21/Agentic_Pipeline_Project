# Cantordust AI Engineer Assessment

## Overview

This repository implements **Task 1 (China → Nepal)** of the Cantordust AI
Engineer assessment as a complete agentic datasheet pipeline. The system ingests
two Deye inverter datasheet PDFs (variants **AM2-P1** and **AM2**), extracts the
specification column for a target model, interprets the evidence, reconciles the
two sources, and produces two deliverables:

- `outputs/structured_output.json` — machine-readable, field-by-field comparison
  with provenance and confidence.
- `outputs/import_draft.md` — a human-readable import draft with conflicts and
  recommended verification questions.

The design deliberately splits the work between **deterministic** stages (fetch,
extract, type-normalize, compare — reliable, reproducible) and **agentic**
stages (LLM field classification and narrative report generation — where
semantic judgment is genuinely needed). Every value carries provenance notes so
every decision can be audited.

## Task Selected

**Task 1 — China → Nepal.** The task is to take the two Deye SUN-4/6/8/10K
datasheet variants provided for this task and produce a clean, import-ready
specification for the **SUN-5K-G06P3** model.

The input URLs (from the task description) are the two official Deye datasheets:

| Source | URL |
|---|---|
| AM2-P1 | `.../datasheet_sun-4-12k-g06p3-eu-am2-p1_231007_en.pdf` |
| AM2 | `.../datasheet_sun-4-15k-g06p3-eu-am2_240318_en.pdf` |

Both datasheets contain a table whose columns are the individual models
(`SUN-4K-G06P3` … `SUN-10K-G06P3`), with some cells **merged across several
model columns**. A correct extraction must respect that merged-cell geometry.

## Architecture

The pipeline is a **linear LangGraph state machine** of seven stages:

```
fetch → extract → evidence → interpret → validate → reconcile → report
```

- **Deterministic layers**: `fetch`, `extract`, `evidence`, `validate`,
  `reconcile` — no randomness, fully reproducible given the same PDFs.
- **Agentic layers**: `interpret` (LLM classifies which canonical field each
  evidence record maps to) and `report` (LLM writes the narrative markdown).
  Both degrade to deterministic fallbacks (rule-based mapper / templated
  markdown) if the LLM is unavailable or fails.

The shared state (`PipelineState`) flows through the graph as a typed dict;
each node writes exactly one key that the next node consumes
(`paths → documents → evidence → canonical → comparisons → report`).

## Pipeline

1. **fetch** — download both PDFs into `cache/`; validate magic bytes, page
   count, and a family marker; raise loudly on any mismatch.
2. **extract** — with `pdfplumber`, locate the model header row via a column
   matcher derived from the target model, measure table column geometry, and
   read each label/value row, detecting merged cells.
3. **evidence** — flatten the extracted rows into one flat list of
   `EvidenceRecord`s (raw label, raw value, page, model, merged-cell flags,
   notes) with their global index preserved.
4. **interpret** — the LLM assigns each record to a canonical field and
   confidence. Values are still **typed deterministically** by the normalizer
   (the model can never invent a number). Falls back to the deterministic
   mapper without a key.
5. **validate** — cross-check every LLM assignment against the deterministic
   mapper; cap confidence where they disagree and where merged cells do not
   cover the target model.
6. **reconcile** — deterministic comparison per canonical field: `agrees`,
   `conflict`, `source_1_only`, `source_2_only`, or `uncertain`.
7. **report** — write `structured_output.json` (always deterministic) and
   `import_draft.md` (LLM narrative with deterministic fallback).

## Tech Stack

- **Python 3.11+**
- **LangGraph** — graph orchestration and shared typed state
- **pdfplumber** — PDF text-layer extraction and table geometry measurement
- **Pydantic v2** — schemas and validation
- **Groq** — LLM inference (`llama-3.3-70b-versatile`), used only for field
  classification and report prose
- **python-dotenv** — environment loading
- Standard library (`urllib`) for fetching — no HTTP dependency needed

## Installation

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows
pip install -r requirements.txt
```

`requirements.txt`:

```
pdfplumber
pydantic>=2
groq
langgraph
python-dotenv
```

## Environment Variables

Create a `.env` file at the project root:

```
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

- `GROQ_API_KEY` — required for the LLM interpretation and report steps. If
  absent, the pipeline runs fully deterministically.
- `GROQ_MODEL` — the model id. Defaults to `llama-3.3-70b-versatile` if unset.
  A **non-reasoning** model is strongly recommended. The original model,
  `qwen/qwen3.6-27b` (a reasoning model), was measurably **inefficient and
  fragile** on this task:
  - it emitted a long `<thinking>` block before every answer, spending
    ~2.5k–4k of the `max_tokens` budget on reasoning alone — roughly doubling
    the token-per-day burn and adding seconds of latency per call;
  - because Groq caps each request at 8000 `input + max_tokens` tokens, the
    thinking block frequently pushed responses past the cap, causing truncated
    answers (`finish_reason: length`) that broke JSON parsing in
    interpretation and produced reports containing only the thinking block;
  - its thinking length was stochastic, so the failures were intermittent and
    hard to reproduce.
  `llama-3.3-70b-versatile` answers directly (no thinking block), so outputs
  are small, fast, and reliably complete, and it comfortably fits the token
  budget. **Caveat:** if `llama-3.3-70b-versatile` becomes unavailable and a
  reasoning model (or `qwen/qwen3.6-27b`) is configured again, this
  inefficiency and the truncation/413 failures will recur. The pipeline keeps
  mitigations for that case (thinking-block stripping, per-chunk re-prompting
  on truncation, deterministic fallback), but they reduce rather than
  eliminate the problem — the correct long-term fix is the provider-abstraction
  enhancement described below.

`.env` is git-ignored; never commit it.

## Running the Pipeline

```powershell
python main.py
```

Without a `GROQ_API_KEY` the pipeline produces identical deliverables using the
deterministic mapper and the templated markdown renderer. With a key, the LLM
steps run, subject to Groq free-tier limits:

- **TPM (tokens/minute)**: the provider counts `input + max_tokens` per request
  against an 8000-token budget. Evidence is sent in chunks of 20 records with a
  10-second pause; interpretation uses `max_tokens=4600` and the report uses a
  compacted payload with `max_tokens=6000`. A chunk whose response is truncated
  (reasoning models only) is re-prompted automatically.
- **TPD (tokens/day)**: the free tier is ~200k tokens/day, and it also counts
  the `max_tokens` reservation per request. When the quota is exhausted the
  LLM steps raise a rate-limit error and the pipeline falls back to the
  deterministic path; a brief note (not the raw API error) is prepended to the
  markdown report as a
  deliberate transparency marker.

## Output Structure

```
outputs/
├── structured_output.json   # machine-readable comparison
├── import_draft.md          # human-readable import draft
├── evidence_am2_p1.json     # extracted evidence dump (tests/dump_evidence.py)
└── evidence_am2.json
```

`structured_output.json`:

```json
{
  "target_model": "SUN-5K-G06P3",
  "source_labels": {"am2_p1": "AM2-P1", "am2": "AM2"},
  "fields": [
    {
      "field": "max_dc_input_current_a",
      "source_1": { "source_id": "am2_p1", "page": 2, "raw": "20+20",
                    "value": [20.0, 20.0], "unit": "A",
                    "confidence": "low",
                    "notes": "merged cell covers: SUN-4K-G06P3, ..." },
      "source_2": { "source_id": "am2", "page": 2, "raw": "13+13",
                    "value": [13.0, 13.0], "unit": "A",
                    "confidence": "low",
                    "notes": "merged cell covers: SUN-4K-G06P3, ..." },
      "status": "conflict",
      "confidence": "low",
      "notes": "merged/shared cells explicitly cover target model; conflict kept at low confidence"
    }
  ]
}
```

`import_draft.md` has five sections: field comparison table, conflicts, present
in one source only, unclear/low-confidence, and recommended verification
questions.

## Extraction Strategy

- The table's model header row is located with a **column matcher derived from
  the target model** (`SUN-5K-G06P3` → `SUN-\d+K-G06P3`), generated at runtime
  from configuration — never a hardcoded literal.
- Column geometry is measured from word positions (`x0`), tiled into contiguous
  intervals; each cell is assigned to the column whose interval contains it.
- **Merged cells** are detected via the geometry and annotated with the set of
  model columns they cover (`merged cell covers: ...`), which later gates
  confidence.
- Values are normalized **by value type** (number, percentage, range/list,
  standard-code lists) by the deterministic normalizer; `raw` text is preserved
  alongside the typed `value` and the `unit`.

## Agent Design

- **Scope limitation**: the LLM only classifies each evidence record into a
  canonical field and assigns a confidence. It never produces values — the
  normalizer types the raw text. This structurally prevents hallucinated specs.
- **Constrained vocabulary**: the system prompt restricts `field` to the exact
  canonical field list (or `null` for garbled/unreadable labels) and forbids
  modifying values.
- **Merged-cell guidance**: the prompt tells the model a merged record may still
  apply to the target model, so shared cells are not discarded.
- **Chunked, paced inference**: records are sent 20-at-a-time with pauses to
  respect the free-tier token budget; rate-limit errors trigger exponential
  sleeps and retries, and a chunk whose response is truncated or unparsable is
  re-prompted before falling back.
- **Deterministic coverage floor**: after the LLM pass, every `(field, source)`
  pair the rule-based mapper would have captured is guaranteed to be present —
  a record the LLM skipped or mis-assigned is filled in from the mapper, so the
  LLM path can never silently drop a value (e.g. turn an `agrees` into
  `source_1_only`).
- **Robust parsing**: the model may wrap its answer in a `<thinking>` block;
  `_parse_assignments` scans for the first valid JSON value with
  `json.JSONDecoder.raw_decode` instead of brittle regex.
- **Validation**: a dedicated node cross-checks every LLM assignment against
  the deterministic mapper, appends `validated: deterministic mapper agrees` or
  caps confidence on disagreement, and caps merged cells that do not cover the
  target model.

## Reconciliation Strategy

Reconciliation is **fully deterministic** — the same inputs always produce the
same verdicts:

- Records are grouped by canonical field, then by source. Per source, the
  highest-confidence record wins; conflicting same-confidence records inside
  one source are flagged as internal inconsistencies.
- **Standard-code fields** (grid standards, safety/EMC) are compared as sets:
  equal sets → `agrees`; one a superset → `conflict` with an explicit note
  (`am2 lists superset of standards (10 vs 3 codes)`).
- **Scalar/text fields** are compared with lexical normalization only
  (whitespace + case) — deliberately **no synonym map**, so no hidden semantic
  assumptions are baked in. Case-only differences (e.g. `Connectors` vs
  `connectors`) produce `agrees` with a transparency note.
- Cross-source confidence is **pessimistic**: a field is only as trustworthy as
  its weaker source.
- A low-confidence conflict between two merged cells is promoted to a kept
  `conflict` only when both cells **explicitly** cover the target model;
  otherwise it is demoted to `uncertain`.

## Handling Uncertainty

- **Confidence model**: every value carries `high` / `medium` / `low`, set by
  the LLM and **only ever capped downward** by the validator.
- **Merged-cell coverage**: a merged value not covering the target model is
  capped to `low` and annotated.
- **`uncertain` status**: low-confidence conflicts that cannot be asserted are
  reported as `uncertain` rather than false conflicts.
- **Verification questions**: every conflict is echoed in the report as a
  concrete question for a human reviewer (`which value applies to SUN-5K-G06P3?`).
- **Provenance everywhere**: raw text, page, notes, and the LLM interpretation
  are preserved so each decision is reproducible and auditable.

## Assumptions

- **`TARGET_MODEL` and `SOURCE_ORDER` come from the task description, not from
  the PDFs.** The task asks for an import-ready spec of `SUN-5K-G06P3` with
  `AM2-P1` treated as the primary variant — these are the assessment's
  requirements, not values read out of the documents. They are applied only at
  **wiring/composition time** in `main.py` (which column to extract, which
  document is "Source 1") and are never consulted at runtime to decide a
  value or verdict. No spec value, status, or confidence depends on them in a
  way that could leak the answer; every output value is computed from the PDF
  text.
- The PDFs provide a machine-readable text layer (no OCR is needed).
- Both variants use the same table layout, so geometric column measurement
  applies to both.
- A merged/shared cell means one value applies to all covered model columns.
- `AM2-P1` (as the first-listed source) is the primary reference; `AM2` is
  secondary.

## Known Limitations

- **Groq free-tier quotas**: TPM pacing keeps requests within budget, but the
  ~200k-token **daily** limit eventually triggers the deterministic fallback.
  This is a **free-tier quota artifact, not a design flaw** — the pipeline is
  deliberately built to degrade gracefully: with a key the LLM enhances the
  output; without budget it still produces a complete, correct deliverable
  (the `agrees`/`conflict` statuses come from the deterministic reconciler in
  both paths). Larger inputs or frequent runs need the Dev tier or a different
  provider.
- **LLM classification is not perfect**: on one run the model skipped the AM2
  record for `max_active_power_kw`, which the deterministic path correctly
  recovers. Validation catches disagreements but cannot fix a skipped record.
- **Model-dependent reliability**: the current configuration depends on
  `llama-3.3-70b-versatile` being a non-reasoning model. If that model (or the
  non-reasoning behavior of the configured model) is unavailable, the
  reasoning-model inefficiencies — long `<thinking>` blocks, higher token
  burn, and truncation/413 failures under the 8000-token per-request cap —
  recur. The pipeline's mitigations (thinking stripping, per-chunk retries,
  deterministic fallback) reduce but do not eliminate these; the durable fix
  is the provider-abstraction enhancement listed under What I Would Improve.
- **No OCR**: scanned/image-only PDFs would fail extraction.
- **Geometry-based extraction** assumes a consistent table layout; a radically
  different layout would need new geometry heuristics.
- **No automated test suite yet** — `tests/` currently contains the evidence
  dump utility; a pytest suite is the primary improvement item.
- **Percentage rendering**: `<3%` is stored as `0.03` with unit `%` (fraction
  semantics); consumers must render it as `3%`.

## Edge Cases

- **Wrong/failed download** → `FetchError` (bad magic bytes, no pages, missing
  family marker) aborts the run loudly instead of producing garbage.
- **Garbled or unreadable labels** → `null` assignment → record skipped with a
  note.
- **Internal inconsistency** (two same-confidence values for one field in one
  source) → flagged in the comparison notes.
- **Merged cell not covering the target** → confidence capped to `low`.
- **Rate limit / daily cap** → retry with backoff, then deterministic fallback
  (report notes the LLM failure explicitly).
- **Truncated LLM report** → completion check (`finish_reason` + required final
  section present) with one retry.
- **Reasoning-model wrapping** → thinking blocks stripped; JSON scanned, not
  regex-matched.
- **Unicode/symbols** (`°C`, `×`, em-dash, `℃` noise in cells) → handled by
  value-type normalization; files are written as UTF-8.

## What I Would Improve

- **Test suite**: proper pytest coverage for each stage with fixtures built
  from the real PDFs and golden files for the deterministic stages.
- **Configurable invocation**: move `TARGET_MODEL` / `SOURCE_ORDER` to CLI args
  or environment with sensible defaults so the same engine runs any model /
  any source pair without editing code.
- **Token-aware chunking**: estimate tokens per chunk from the actual payload
  instead of a fixed 20-record size.
- **Provider abstraction**: a pluggable LLM client so the pipeline can route to
  another provider (or a paid tier) when one provider's quota is exhausted —
  the direct resolution to the daily-cap fallback.
- **OCR fallback**: a `pytesseract` path for scanned documents.
- **Concurrent, paced LLM calls** with a proper token-budget scheduler rather
  than sequential sleeps.
- **Stronger merged-cell semantics**: infer partial coverage more precisely and
  surface it in the report.
- **Richer typing**: render percentages as `%` (display `3%`, store `0.03`).
- **Third-source cross-check** against a second datasheet family for
  independent validation of `agrees` fields.

## Example Output

From the live run (`structured_output.json`, 35 fields —
24 `agrees` / 8 `conflict` / 2 `source_1_only` / 1 `source_2_only`):

```json
{
  "field": "euro_efficiency_pct",
  "source_1": { "raw": "97.5%", "value": 0.975, "unit": "%", "confidence": "high" },
  "source_2": { "raw": "97.6%", "value": 0.976, "unit": "%", "confidence": "low",
                "notes": "merged cell covers: SUN-5K-G06P3, SUN-6K-G06P3, SUN-7K-G06P3; ..." },
  "status": "conflict",
  "confidence": "low",
  "notes": "merged/shared cells explicitly cover target model; conflict kept at low confidence"
}
```

Corresponding `import_draft.md` entry:

```markdown
- **euro_efficiency_pct**: which value applies to SUN-5K-G06P3? (0.975 vs 0.976)
```