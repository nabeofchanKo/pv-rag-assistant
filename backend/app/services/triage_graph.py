"""LangGraph orchestration of the case-triage pipeline (Phase 4a + 4b HITL).

Wraps the six evaluation services (already built + DI'd in ``dependencies.py``)
into an explainable ``StateGraph``, then adds a human-in-the-loop approval gate.
Ingestion stays at the router boundary (temp-file lifecycle + HTTP error
mapping); the graph operates over the case ``text`` and returns the triage
results.

Honest dependency DAG (drives the fan-out) + the Phase 4b review gate::

    START ─┬─> product_match ──┬─> causality ─────┐
           └─> extraction ─────┼─> expectedness ──┤   (3 assessments join)
                     └─> meddra ─> seriousness ────┤
                                                   ▼
                                            human_review   ← interrupt(): a human
                                                   │          approves / overrides
                                                   ▼
                                              finalize      ← apply overrides + audit
                                                   │
                                                   ▼
                                                  END

* ``product_match`` and ``extraction`` only need the text, so they run in
  parallel from START.
* ``meddra`` needs the extracted terms; ``seriousness`` needs the coded PTs
  (criterion 6 / IME) on top of extraction, so it sits after ``meddra``.
* ``causality`` and ``expectedness`` join on ``[product_match, extraction]`` and
  run in parallel with the ``meddra → seriousness`` branch.
* ``human_review`` calls ``interrupt()`` to pause for a reviewer (needs a
  checkpointer). ``auto_approve`` in the input state skips the pause (used by
  the wiring tests and any non-HITL/batch caller) so the graph also runs to
  completion with no checkpointer.
* ``finalize`` applies the reviewer's verdict overrides to the assessments,
  records an auditable trail (original → new verdict), and sets ``status``.

Each assessment node writes a **distinct** state key, so the parallel branches
never conflict and no channel reducer is needed. See ADR 0006 / 0007.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.schemas import (
    CaseExtraction,
    CausalityAssessment,
    DrugExpectedness,
    Escalation,
    EventPrecedent,
    ImePromotionRecord,
    MeddraCoding,
    OverrideRecord,
    ProductMatchResult,
    ReviewOutcome,
    SeriousnessAssessment,
)
from app.services.causality import CausalityService
from app.services.expectedness import ExpectednessService
from app.services.extraction import ExtractionService
from app.services.meddra_coding import MeddraCodingService
from app.services.precedent import PrecedentService
from app.services.product_master import ProductMasterService
from app.services.seriousness import SeriousnessService

# Allowed verdicts per review axis — pins what a reviewer may override a value to
# (and what counts as a valid escalation band). Kept here so the router can
# validate an incoming override before it reaches the graph.
ALLOWED_VERDICTS: dict[str, set[str]] = {
    "seriousness": {"重篤", "非重篤", "要確認"},
    "causality": {"否定できない", "否定できる", "評価不能"},
    "expectedness": {"既知", "要確認", "未知", "判定不能"},
}


class TriageState(TypedDict, total=False):
    """Shared state flowing through the triage graph.

    ``text`` is the only required input; every other key is filled in by the
    node named after it. ``total=False`` lets each node return a partial update.
    """

    # --- input ---
    text: str
    document_name: str
    auto_approve: bool  # skip the human-review interrupt (non-HITL / batch)
    # --- per-node outputs ---
    product_match: ProductMatchResult
    extraction: CaseExtraction
    meddra: list[MeddraCoding]
    seriousness: list[SeriousnessAssessment]
    causality: list[CausalityAssessment]
    expectedness: list[DrugExpectedness]
    precedent: list[EventPrecedent]  # Phase 4d: past-case precedent (advisory)
    # --- HITL (Phase 4b) ---
    review: dict  # the reviewer's ReviewDecision (dump), handed back via resume
    status: str  # "approved" | "rejected"
    review_outcome: ReviewOutcome  # audit trail attached to the final result


# --- pure helpers (unit-testable without the graph) ---


def compute_escalations(
    seriousness: list[SeriousnessAssessment],
    causality: list[CausalityAssessment],
    expectedness: list[DrugExpectedness],
    precedent: list[EventPrecedent] | None = None,
) -> list[Escalation]:
    """The items a reviewer should decide on: the safe-side uncertain bands, plus
    (Phase 4d) events where the draft disagrees with past-case precedent.

    Uncertain bands are the HITL hooks we built: 要確認 (seriousness / expectedness)
    and 評価不能 (causality). 否定できない is the conservative default for most events,
    so it is reviewable but not flagged (that would drown the signal). Precedent
    conflicts surface inconsistency vs prior approved cases.
    """
    out: list[Escalation] = []
    for s in seriousness:
        if s.verdict == "要確認":
            out.append(
                Escalation(
                    axis="seriousness",
                    term=s.term,
                    verdict=s.verdict,
                    reason="重篤性が確定できず安全側で要確認（HITL判断が必要）",
                )
            )
    for c in causality:
        if c.verdict == "評価不能":
            out.append(
                Escalation(
                    axis="causality",
                    term=c.term,
                    verdict=c.verdict,
                    reason="日付不足で時間関係を確立できず評価不能",
                )
            )
    for de in expectedness:
        for a in de.assessments:
            if a.verdict == "要確認":
                out.append(
                    Escalation(
                        axis="expectedness",
                        term=a.term,
                        drug_name=de.drug_name,
                        verdict=a.verdict,
                        reason="既知/未知が確定できず安全側で要確認（HITL判断が必要）",
                    )
                )
    # Phase 4d: flag events whose current verdict differs from precedent majority.
    ser_now = {s.term: s.verdict for s in seriousness}
    cau_now = {c.term: c.verdict for c in causality}
    for ep in precedent or []:
        for axis in ep.conflicts:
            counts = ep.seriousness if axis == "seriousness" else ep.causality
            summary = "／".join(f"{v}{n}件" for v, n in counts.items())
            current = ser_now.get(ep.term) if axis == "seriousness" else cau_now.get(ep.term)
            out.append(
                Escalation(
                    axis=axis,
                    term=ep.term,
                    verdict=current or "—",
                    reason=f"過去症例と不一致（今回: {current}／過去 {ep.n_cases}件: {summary}）",
                )
            )
    return out


def apply_overrides(
    *,
    seriousness: list[SeriousnessAssessment],
    causality: list[CausalityAssessment],
    expectedness: list[DrugExpectedness],
    overrides: list[dict],
) -> tuple[
    list[SeriousnessAssessment],
    list[CausalityAssessment],
    list[DrugExpectedness],
    list[OverrideRecord],
]:
    """Apply a reviewer's verdict overrides, returning new lists + audit records.

    Non-destructive: builds copies, keeps the original verdict in each record.
    An override that matches nothing (unknown term/drug) is silently skipped —
    the router validates verdict values up front, so a miss here means a stale
    reference, not bad input.
    """
    seriousness = list(seriousness)
    causality = list(causality)
    expectedness = list(expectedness)
    records: list[OverrideRecord] = []

    for ov in overrides:
        axis = ov.get("axis")
        term = ov.get("term")
        new = ov.get("new_verdict")
        rationale = ov.get("rationale")
        if not (axis and term and new):
            continue

        if axis == "seriousness":
            for i, a in enumerate(seriousness):
                if a.term == term:
                    records.append(
                        OverrideRecord(
                            axis=axis, term=term, original_verdict=a.verdict,
                            new_verdict=new, rationale=rationale,
                        )
                    )
                    seriousness[i] = a.model_copy(update={"verdict": new})
                    break

        elif axis == "causality":
            for i, a in enumerate(causality):
                if a.term == term:
                    records.append(
                        OverrideRecord(
                            axis=axis, term=term, original_verdict=a.verdict,
                            new_verdict=new, rationale=rationale,
                        )
                    )
                    causality[i] = a.model_copy(update={"verdict": new})
                    break

        elif axis == "expectedness":
            drug = ov.get("drug_name")
            for j, de in enumerate(expectedness):
                if drug and de.drug_name != drug:
                    continue
                assessments = list(de.assessments)
                hit = False
                for i, a in enumerate(assessments):
                    if a.term == term:
                        records.append(
                            OverrideRecord(
                                axis=axis, term=term, drug_name=de.drug_name,
                                original_verdict=a.verdict, new_verdict=new,
                                rationale=rationale,
                            )
                        )
                        assessments[i] = a.model_copy(update={"verdict": new})
                        hit = True
                        break
                if hit:
                    expectedness[j] = de.model_copy(update={"assessments": assessments})
                    break

    return seriousness, causality, expectedness, records


def build_triage_graph(
    *,
    product_master: ProductMasterService,
    extraction: ExtractionService,
    meddra: MeddraCodingService,
    seriousness: SeriousnessService,
    causality: CausalityService,
    expectedness: ExpectednessService,
    precedent: PrecedentService,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Assemble and compile the triage graph from the six evaluation services.

    ``checkpointer`` is required for the HITL interrupt/resume flow (the app
    passes a SqliteSaver); omit it only for auto-approve / run-to-completion
    use (e.g. wiring tests). ``dependencies.get_triage_graph`` builds it once.
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

    def precedent_node(state: TriageState) -> dict:
        pm = state.get("product_match")
        drugs = [p.name for p in pm.matched_products] if pm else []
        meddra = state.get("meddra", [])
        if not meddra:
            return {"precedent": []}
        return {
            "precedent": precedent.summarize(
                drugs,
                meddra,
                state.get("seriousness", []),
                state.get("causality", []),
                state.get("expectedness", []),
            )
        }

    def human_review_node(state: TriageState) -> dict:
        """Pause for a human reviewer (unless auto_approve). Kept side-effect free
        before ``interrupt`` because the node re-runs from the top on resume."""
        if state.get("auto_approve"):
            return {}
        escalations = compute_escalations(
            state.get("seriousness", []),
            state.get("causality", []),
            state.get("expectedness", []),
            state.get("precedent", []),
        )
        decision = interrupt(
            {
                "reason": "triage draft ready for review",
                "escalations": [e.model_dump() for e in escalations],
            }
        )
        return {"review": decision}

    def finalize_node(state: TriageState) -> dict:
        decision = state.get("review") or {"action": "approve", "reviewer": "auto"}
        action = decision.get("action", "approve")
        reviewer = decision.get("reviewer", "auto")
        # IME promotions are performed + resolved in the router (a reference-side
        # effect); finalize only records them in the audit trail.
        promotions = [
            ImePromotionRecord(**r) for r in decision.get("ime_promotion_records", [])
        ]

        if action == "reject":
            outcome = ReviewOutcome(
                status="rejected", reviewer=reviewer, note=decision.get("note"),
                overrides=[], ime_promotions=promotions, reviewed_at=datetime.now(),
            )
            return {"status": "rejected", "review_outcome": outcome}

        seriousness_f, causality_f, expectedness_f, records = apply_overrides(
            seriousness=state.get("seriousness", []),
            causality=state.get("causality", []),
            expectedness=state.get("expectedness", []),
            overrides=decision.get("overrides", []),
        )
        outcome = ReviewOutcome(
            status="approved", reviewer=reviewer, note=decision.get("note"),
            overrides=records, ime_promotions=promotions, reviewed_at=datetime.now(),
        )
        return {
            "seriousness": seriousness_f,
            "causality": causality_f,
            "expectedness": expectedness_f,
            "status": "approved",
            "review_outcome": outcome,
        }

    graph = StateGraph(TriageState)
    graph.add_node("product_match", product_match_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("meddra", meddra_node)
    graph.add_node("seriousness", seriousness_node)
    graph.add_node("causality", causality_node)
    graph.add_node("expectedness", expectedness_node)
    graph.add_node("precedent", precedent_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("finalize", finalize_node)

    # product_match ∥ extraction fan out from START.
    graph.add_edge(START, "product_match")
    graph.add_edge(START, "extraction")
    # meddra → seriousness chain (seriousness also reads extraction, already done).
    graph.add_edge("extraction", "meddra")
    graph.add_edge("meddra", "seriousness")
    # causality / expectedness join on both product_match AND extraction.
    graph.add_edge(["product_match", "extraction"], "causality")
    graph.add_edge(["product_match", "extraction"], "expectedness")
    # All three assessment branches join at the precedent lookup (needs the
    # verdicts + coded PTs), which then feeds the human-review gate.
    graph.add_edge(["seriousness", "causality", "expectedness"], "precedent")
    graph.add_edge("precedent", "human_review")
    graph.add_edge("human_review", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
