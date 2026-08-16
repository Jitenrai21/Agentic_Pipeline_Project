"""Agentic datasheet pipeline.

Linear LangGraph flow:
    PDF -> deterministic extraction -> evidence -> LLM structured extraction
        -> validation -> deterministic comparison -> LLM report generation
Run:  python main.py
Requires GROQ_API_KEY for the LLM interpretation and report steps; without it
the deterministic mapper / markdown renderer are used as fallback.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.pipeline.agent import interpret
from src.pipeline.evidence import to_evidence
from src.pipeline.extractor import extract
from src.pipeline.fetcher import fetch
from src.pipeline.reconciler import reconcile
from src.pipeline.reporter import report
from src.pipeline.schemas import Source
from src.pipeline.validate import validate

load_dotenv()

SOURCES = [
    Source(id="am2_p1", label="AM2-P1",
           url="https://www.deyeinverter.com/deyeinverter/2023/10/07/datasheet_sun-4-12k-g06p3-eu-am2-p1_231007_en.pdf",
           variant_hint="AM2-P1"),
    Source(id="am2", label="AM2",
           url="https://www.deyeinverter.com/deyeinverter/2024/03/20/datasheet_sun-4-15k-g06p3-eu-am2_240318_en.pdf",
           variant_hint="AM2"),
]

TARGET_MODEL = "SUN-5K-G06P3"
SOURCE_ORDER = ("am2_p1", "am2")
CACHE_DIR = Path("cache")
OUTPUT_DIR = Path("outputs")


class PipelineState(TypedDict, total=False):
    paths: list[Path]
    documents: list
    evidence: list
    canonical: list
    comparisons: list
    report: dict


def fetch_node(state: PipelineState) -> dict:
    paths = [fetch(s, CACHE_DIR, expected_family="SUN-") for s in SOURCES]
    return {"paths": paths}


def extract_node(state: PipelineState) -> dict:
    documents = [extract(p, s.id, TARGET_MODEL) for p, s in zip(state["paths"], SOURCES)]
    return {"documents": documents}


def evidence_node(state: PipelineState) -> dict:
    evidence: list = []
    for doc in state["documents"]:
        evidence += to_evidence(doc, TARGET_MODEL)
    return {"evidence": evidence}


def interpret_node(state: PipelineState) -> dict:
    return {"canonical": interpret(state["evidence"], TARGET_MODEL)}


def validate_node(state: PipelineState) -> dict:
    validated = validate(state["canonical"], state["evidence"], TARGET_MODEL)
    return {"canonical": validated}


def reconcile_node(state: PipelineState) -> dict:
    comparisons = reconcile(state["canonical"],
                            source_order=SOURCE_ORDER,
                            target_model=TARGET_MODEL)
    return {"comparisons": comparisons}


def report_node(state: PipelineState) -> dict:
    labels = {s.id: s.label for s in SOURCES}
    payload = report(state["comparisons"], TARGET_MODEL, OUTPUT_DIR, labels)
    return {"report": payload}


def build_graph():
    graph = StateGraph(PipelineState)
    nodes = [
        ("fetch", fetch_node),
        ("extract", extract_node),
        ("evidence", evidence_node),
        ("interpret", interpret_node),
        ("validate", validate_node),
        ("reconcile", reconcile_node),
        ("report", report_node),
    ]
    for name, fn in nodes:
        graph.add_node(name, fn)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "extract")
    graph.add_edge("extract", "evidence")
    graph.add_edge("evidence", "interpret")
    graph.add_edge("interpret", "validate")
    graph.add_edge("validate", "reconcile")
    graph.add_edge("reconcile", "report")
    graph.add_edge("report", END)
    return graph.compile()


def main() -> int:
    compiled = build_graph()
    result = compiled.invoke({})
    fields = len(result["comparisons"])
    print(f"done: {fields} fields -> {OUTPUT_DIR / 'structured_output.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())