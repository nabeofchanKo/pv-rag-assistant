"""LangGraph orchestration of the case-triage pipeline (Phase 4a).

Wraps the six evaluation services (already built + DI'd in ``dependencies.py``)
into an explainable ``StateGraph``. Ingestion stays at the router boundary
(temp-file lifecycle + HTTP error mapping); the graph operates purely over the
case ``text`` and returns the triage results.

Honest dependency DAG (drives the fan-out below)::

    START ─┬─> product_match ──┬─> causality
           │                   ├─> expectedness
           └─> extraction ─────┘        │
                     │                  │
                     └─> meddra ─> seriousness
                                         │
    (all of seriousness / causality / expectedness) ─> END

* ``product_match`` and ``extraction`` only need the text, so they run in
  parallel from START.
* ``meddra`` needs the extracted terms; ``seriousness`` needs the coded PTs
  (criterion 6 / IME) on top of extraction, so it sits after ``meddra``.
* ``causality`` and ``expectedness`` need both the matched products and the
  extraction, so they join on ``[product_match, extraction]`` and run in
  parallel with the ``meddra → seriousness`` branch.

Each assessment node writes a **distinct** state key, so the parallel branches
never conflict and no channel reducer is needed.

Behaviour is identical to the previous imperative router — Phase 4a is a
structural migration verified by parity (see ``tests/test_triage_graph.py``).
HITL interrupt/resume + a SqliteSaver checkpointer land in Phase 4b.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.schemas import (
    CaseExtraction,
    CausalityAssessment,
    DrugExpectedness,
    MeddraCoding,
    ProductMatchResult,
    SeriousnessAssessment,
)
from app.services.causality import CausalityService
from app.services.expectedness import ExpectednessService
from app.services.extraction import ExtractionService
from app.services.meddra_coding import MeddraCodingService
from app.services.product_master import ProductMasterService
from app.services.seriousness import SeriousnessService


class TriageState(TypedDict, total=False):
    """Shared state flowing through the triage graph.

    ``text`` is the only required input; every other key is filled in by the
    node named after it. ``total=False`` lets each node return a partial update.
    """

    # --- input ---
    text: str
    document_name: str
    # --- per-node outputs ---
    product_match: ProductMatchResult
    extraction: CaseExtraction
    meddra: list[MeddraCoding]
    seriousness: list[SeriousnessAssessment]
    causality: list[CausalityAssessment]
    expectedness: list[DrugExpectedness]


def build_triage_graph(
    *,
    product_master: ProductMasterService,
    extraction: ExtractionService,
    meddra: MeddraCodingService,
    seriousness: SeriousnessService,
    causality: CausalityService,
    expectedness: ExpectednessService,
) -> CompiledStateGraph:
    """Assemble and compile the triage graph from the six evaluation services.

    The services are captured by the node closures, so the returned graph is a
    ready-to-invoke object; ``dependencies.get_triage_graph`` builds it once and
    caches it. No checkpointer here (Phase 4a runs to completion via
    ``invoke``); Phase 4b compiles with a SqliteSaver + ``interrupt`` for HITL.
    """

    def product_match_node(state: TriageState) -> dict:
        return {"product_match": product_master.match(state["text"])}

    def extraction_node(state: TriageState) -> dict:
        return {"extraction": extraction.extract(state["text"])}

    def meddra_node(state: TriageState) -> dict:
        terms = [ae.term for ae in state["extraction"].adverse_events]
        return {"meddra": meddra.code(terms) if terms else []}

    def seriousness_node(state: TriageState) -> dict:
        events = state["extraction"].adverse_events
        results = (
            seriousness.assess(state["text"], events, state["meddra"])
            if events
            else []
        )
        return {"seriousness": results}

    def causality_node(state: TriageState) -> dict:
        events = state["extraction"].adverse_events
        suspect_drugs = [p.name for p in state["product_match"].matched_products]
        results = (
            causality.assess(state["text"], events, suspect_drugs) if events else []
        )
        return {"causality": results}

    def expectedness_node(state: TriageState) -> dict:
        terms = [ae.term for ae in state["extraction"].adverse_events]
        results = [
            expectedness.assess(p.name, p.label_document, terms)
            for p in state["product_match"].matched_products
            if p.label_document and terms
        ]
        return {"expectedness": results}

    graph = StateGraph(TriageState)
    graph.add_node("product_match", product_match_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("meddra", meddra_node)
    graph.add_node("seriousness", seriousness_node)
    graph.add_node("causality", causality_node)
    graph.add_node("expectedness", expectedness_node)

    # product_match ∥ extraction fan out from START.
    graph.add_edge(START, "product_match")
    graph.add_edge(START, "extraction")
    # meddra → seriousness chain (seriousness also reads extraction, already done).
    graph.add_edge("extraction", "meddra")
    graph.add_edge("meddra", "seriousness")
    # causality / expectedness join on both product_match AND extraction.
    graph.add_edge(["product_match", "extraction"], "causality")
    graph.add_edge(["product_match", "extraction"], "expectedness")
    # All three assessment branches converge on END.
    graph.add_edge("seriousness", END)
    graph.add_edge("causality", END)
    graph.add_edge("expectedness", END)

    return graph.compile()
