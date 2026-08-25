"""
Agentic Pipeline — LangGraph Orchestration
Main entry point using LangGraph for state management.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, END

from src.pipeline.config import SOURCES
from src.pipeline.fetcher import fetch_documents
from src.pipeline.model_finder import ModelMatch
from src.pipeline.field_extractor import extract_from_cached
from src.pipeline.reconciliation import reconcile_fields, print_reconciliation
from src.pipeline.report import generate_json_report, generate_markdown_report
from src.pipeline.schemas import TASK1_FIELDS


# ── State definition ────────────────────────────────────────────────

class PipelineState(TypedDict):
    """State for the pipeline graph."""
    requested_model: str
    pdfs: dict
    extractions: dict
    reconciliation: object
    reports: dict
    status: str


# ── Node functions ──────────────────────────────────────────────────

def fetch_documents_node(state: PipelineState) -> PipelineState:
    """Node: Fetch source documents."""
    print("\n[1/5] Fetching documents...")
    state["pdfs"] = fetch_documents()
    state["status"] = "fetched"
    return state


def extract_source_1_node(state: PipelineState) -> PipelineState:
    """Node: Extract fields from source 1."""
    print("\n[2/5] Extracting from Source 1...")
    
    doc_id = "source_1"
    if doc_id not in state["pdfs"]:
        print(f"  {doc_id} not found")
        return state
    
    doc_info = state["pdfs"][doc_id]
    variant = doc_info.get("variant", "")
    
    model_match = ModelMatch(
        requested=state["requested_model"],
        matched_model=state["requested_model"],
        variant=variant,
        confidence=0.95,
        source_document=doc_id,
    )
    
    result = extract_from_cached(doc_id, model_match, use_llm_fallback=False)
    
    fields_dict = {}
    for field_name, val in result.fields.items():
        fields_dict[field_name] = {
            "value": val.value,
            "unit": val.unit,
            "source": val.source,
        }
    
    state["extractions"][doc_id] = {
        "variant": variant,
        "fields": fields_dict,
    }
    
    extracted_count = sum(1 for v in result.fields.values() if v.source == "table")
    print(f"  {doc_id}: {extracted_count} fields extracted")
    
    return state


def extract_source_2_node(state: PipelineState) -> PipelineState:
    """Node: Extract fields from source 2."""
    print("\n[3/5] Extracting from Source 2...")
    
    doc_id = "source_2"
    if doc_id not in state["pdfs"]:
        print(f"  {doc_id} not found")
        return state
    
    doc_info = state["pdfs"][doc_id]
    variant = doc_info.get("variant", "")
    
    model_match = ModelMatch(
        requested=state["requested_model"],
        matched_model=state["requested_model"],
        variant=variant,
        confidence=0.95,
        source_document=doc_id,
    )
    
    result = extract_from_cached(doc_id, model_match, use_llm_fallback=False)
    
    fields_dict = {}
    for field_name, val in result.fields.items():
        fields_dict[field_name] = {
            "value": val.value,
            "unit": val.unit,
            "source": val.source,
        }
    
    state["extractions"][doc_id] = {
        "variant": variant,
        "fields": fields_dict,
    }
    
    extracted_count = sum(1 for v in result.fields.values() if v.source == "table")
    print(f"  {doc_id}: {extracted_count} fields extracted")
    
    return state


def reconcile_node(state: PipelineState) -> PipelineState:
    """Node: Reconcile fields from both sources."""
    print("\n[4/5] Reconciling sources...")
    
    doc_ids = list(state["extractions"].keys())
    if len(doc_ids) < 2:
        print("  Need at least 2 sources for reconciliation")
        return state
    
    extraction_a = state["extractions"][doc_ids[0]]["fields"]
    extraction_b = state["extractions"][doc_ids[1]]["fields"]
    variant_a = state["extractions"][doc_ids[0]]["variant"]
    variant_b = state["extractions"][doc_ids[1]]["variant"]
    
    reconciliation = reconcile_fields(
        fields_a=extraction_a,
        fields_b=extraction_b,
        variant_a=variant_a,
        variant_b=variant_b,
        use_llm=False,
    )
    
    state["reconciliation"] = reconciliation
    print_reconciliation(reconciliation)
    
    return state


def report_node(state: PipelineState) -> PipelineState:
    """Node: Generate reports."""
    print("\n[5/5] Generating reports...")
    
    if not state["reconciliation"]:
        print("  No reconciliation data")
        return state
    
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    doc_ids = list(state["extractions"].keys())
    
    # JSON report
    json_path = output_dir / "import_review.json"
    generate_json_report(
        reconciliation=state["reconciliation"],
        extraction_a=state["extractions"][doc_ids[0]]["fields"],
        extraction_b=state["extractions"][doc_ids[1]]["fields"],
        variant_a=state["extractions"][doc_ids[0]]["variant"],
        variant_b=state["extractions"][doc_ids[1]]["variant"],
        output_path=json_path,
    )
    state["reports"]["json"] = str(json_path)
    print(f"  JSON: {json_path}")
    
    # Markdown report
    md_path = output_dir / "import_draft.md"
    generate_markdown_report(
        reconciliation=state["reconciliation"],
        extraction_a=state["extractions"][doc_ids[0]]["fields"],
        extraction_b=state["extractions"][doc_ids[1]]["fields"],
        variant_a=state["extractions"][doc_ids[0]]["variant"],
        variant_b=state["extractions"][doc_ids[1]]["variant"],
        output_path=md_path,
    )
    state["reports"]["markdown"] = str(md_path)
    print(f"  Markdown: {md_path}")
    
    return state


def summary_node(state: PipelineState) -> PipelineState:
    """Node: Print final summary."""
    print("Pipeline Complete!")
    
    print(f"\n  Target Model: {state['requested_model']}")
    print(f"  Sources: {len(state['extractions'])}")
    
    if state["reconciliation"]:
        rec = state["reconciliation"]
        print(f"  Agreements: {len(rec.agreements)}")
        print(f"  Conflicts: {len(rec.conflicts)}")
        print(f"  Source only: {len(rec.source_only)}")
        print(f"  Missing: {len(rec.missing)}")
    
    if state["reports"]:
        print(f"\n  Reports:")
        for report_type, path in state["reports"].items():
            print(f"    {report_type}: {path}")
    
    state["status"] = "complete"
    return state


# ── Build the graph ─────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build the LangGraph pipeline."""
    
    # Create graph
    graph = StateGraph(PipelineState)
    
    # Add nodes
    graph.add_node("fetch", fetch_documents_node)
    graph.add_node("extract_1", extract_source_1_node)
    graph.add_node("extract_2", extract_source_2_node)
    graph.add_node("reconcile", reconcile_node)
    graph.add_node("report", report_node)
    graph.add_node("summary", summary_node)
    
    # Define edges
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "extract_1")
    graph.add_edge("extract_1", "extract_2")
    graph.add_edge("extract_2", "reconcile")
    graph.add_edge("reconcile", "report")
    graph.add_edge("report", "summary")
    graph.add_edge("summary", END)
    
    return graph.compile()


# ── Main entry point ────────────────────────────────────────────────

def run_pipeline(requested_model: str = "5k"):
    """Run the full agentic pipeline using LangGraph."""
    
    print("Agentic Pipeline — LangGraph Orchestration")
    
    # Initial state
    initial_state: PipelineState = {
        "requested_model": requested_model,
        "pdfs": {},
        "extractions": {},
        "reconciliation": None,
        "reports": {},
        "status": "started",
    }
    
    # Build and run graph
    graph = build_graph()
    final_state = graph.invoke(initial_state)
    
    return final_state


if __name__ == "__main__":
    run_pipeline()
