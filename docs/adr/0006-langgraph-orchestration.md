# 0006 — Triage orchestration via a LangGraph StateGraph (workflow, not agent)

- **Status:** Accepted
- **Date:** 2026-08-23
- **Phase:** 4 (orchestration), slice 4a
- **Evidence:** design + parity tests ([backend/tests/test_triage_graph.py](../../backend/tests/test_triage_graph.py))

## Context

Phases 2–3 built six evaluation steps (own-company product match → extraction →
MedDRA coding → seriousness → causality → expectedness), each a standalone,
dependency-injected service. `POST /cases/triage` ran them **imperatively** in the
router: a straight-line script that hard-coded the order, the `terms`-empty
short-circuits, and which upstream output fed which step.

Phase 4's goal is an **explainable, HITL-capable** pipeline (propose → approve) for
a regulated domain. That needs the pipeline to be a first-class object we can
visualise, pause, checkpoint, and resume — not control flow buried in a request
handler.

## Options

1. **Keep the imperative router.** Simplest, but no place to hang a human-approval
   interrupt, no checkpoint/resume, no visualisation, and the dependency structure
   stays implicit.
2. **Autonomous agent (ReAct / tool-calling loop).** The LLM decides which step to
   run next. Rejected earlier (locked 2026-08-19): non-deterministic and hard to
   audit — unacceptable for a safety-reporting workflow.
3. **Workflow-type LangGraph `StateGraph`.** A deterministic, declared graph of
   nodes over a shared typed state. Explainable (the DAG renders), and LangGraph's
   `interrupt` + checkpointers give HITL and resume for free in Phase 4b.

## Decision

Adopt **option 3**. Slice 4a is a **structural migration with behaviour parity** —
no judgment logic changes.

- **State:** `TriageState` (TypedDict, `total=False`); `text` is the only input,
  each node fills the key named after it. Parallel branches write **distinct** keys,
  so no channel reducer is needed.
- **Nodes = the existing services**, captured by closures in
  `build_triage_graph(...)`; `dependencies.get_triage_graph` builds + compiles the
  graph once (`lru_cache`) from the same DI providers as before.
- **Honest fan-out DAG** (not a straight line — it mirrors the real data
  dependencies):
  - `START → product_match` ∥ `extraction`
  - `extraction → meddra → seriousness` (seriousness needs the coded PT for E2A
    criterion 6 / IME)
  - `[product_match, extraction] → causality` and `→ expectedness` (both need the
    matched drug(s) and the extracted events; they run in parallel with the
    meddra→seriousness branch)
  - `seriousness, causality, expectedness → END`
- **Ingestion stays at the router boundary.** File → text, temp-file lifecycle, and
  HTTP error mapping (415/422) are I/O concerns, not evaluation; the graph is pure
  over `text`. The router `invoke`s the graph and assembles `TriageResponse`.
- **No checkpointer in 4a** (run-to-completion `invoke`). Phase 4b compiles with a
  **SqliteSaver** (persistent across restarts) + an `interrupt` for the human
  approval gate; the escalation hooks already exist (要確認 / 否定できない bands, the
  HITL-appendable IME list).

## Consequences

- (+) The pipeline is now a rendered DAG (`get_graph().draw_mermaid()`) —
  self-documenting and portfolio-legible.
- (+) The three independent assessments fan out, so the honest dependency structure
  is explicit and the parallel branches can execute concurrently.
- (+) A clean seam for Phase 4b HITL: `interrupt` before finalising, resume from a
  checkpoint — no router surgery.
- (+) Parity is testable without the API: `test_triage_graph.py` pins the wiring
  (every node runs, coded PTs reach seriousness, suspect drugs reach causality,
  labelled-product-only expectedness, empty-case short-circuits). 36 tests pass.
- (−) Adds `langgraph` as a dependency and a small indirection (state dict vs direct
  calls). Judged worth it for the HITL/explainability payoff.
- Deferred, to fold in later: the MedDRA-PT AND-gate for expectedness (ADR 0002) and
  past-case precedent RAG — both slot in as additional nodes/edges.
