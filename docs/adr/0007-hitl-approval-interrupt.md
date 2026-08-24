# 0007 — HITL approval via LangGraph interrupt/resume + SqliteSaver

- **Status:** Accepted
- **Date:** 2026-08-23
- **Phase:** 4 (orchestration), slice 4b
- **Evidence:** design + interrupt/resume tests ([backend/tests/test_triage_graph.py](../../backend/tests/test_triage_graph.py)) + live E2E (start → draft → approve+override → result)

## Context

Phase 4a turned the triage pipeline into a LangGraph `StateGraph` (ADR 0006).
For a regulated safety-reporting workflow the output must be a **proposal a human
approves**, not an auto-committed verdict — and the review should be able to
*correct* the machine judgment, with an audit trail of what changed. The
uncertain bands we deliberately built (要確認 for seriousness/expectedness,
評価不能 for causality) are the natural escalation points.

## Options

1. **Static gate (`interrupt_before=["finalize"]`) + `update_state`.** Older
   LangGraph pattern; the client must patch state manually to inject the
   decision. More moving parts, decision plumbing is implicit.
2. **Poll a status flag in the app layer.** Keep the graph run-to-completion and
   bolt approval on outside it. Loses the "pipeline is one explainable object"
   property and the free checkpoint/resume.
3. **Dynamic `interrupt()` + `Command(resume=...)` with a checkpointer.** The
   graph pauses inside a `human_review` node, the reviewer's decision is handed
   straight back as the resume value, and a `finalize` node applies it.

## Decision

Adopt **option 3**.

- **Graph:** the three assessment branches join at `human_review → finalize →
  END`. `human_review` calls `interrupt({escalations})`; `finalize` applies the
  reviewer's verdict overrides and records the audit trail.
- **`auto_approve` state flag** (default False) lets `human_review` skip the
  interrupt — so the graph still runs to completion with no checkpointer (wiring
  tests, and any non-HITL/batch caller). HITL is the default for the endpoint.
- **Checkpointer = SqliteSaver** (`backend/checkpoints/triage.sqlite`,
  gitignored), one shared connection (`check_same_thread=False`; SqliteSaver
  locks internally). Persists paused drafts across restarts. Its serializer
  **allow-lists every `app.schemas` Pydantic model** — LangGraph will block
  deserializing unregistered types from a checkpoint in a future version, so we
  register them up front.
- **API (HITL is the product):**
  - `POST /cases/triage` → ingest, start a run (new `thread_id`), return the
    **draft** (`status: awaiting_review`, `escalations`). `?auto_approve=true`
    runs straight through and returns the finalized result.
  - `POST /cases/{thread_id}/approve` → body `ReviewDecision` (approve/reject,
    reviewer, note, overrides). Overrides are validated against the allowed
    verdicts per axis (422 on a bad value); resumes the graph; returns the
    finalized `TriageResult`.
  - `GET /cases/{thread_id}` → reload the draft/result (404 unknown, backed by
    the checkpointer so it survives restarts).
- **Overrides (4b scope):** the three judgment verdicts
  (seriousness/causality/expectedness), each non-destructive — an `OverrideRecord`
  keeps the original verdict. Changing `verdict` auto-updates the computed
  `is_serious` / `is_excludable` / `is_expected` flags. Editing the extraction
  itself (add/remove AE, fix MedDRA) is deferred.

## Consequences

- (+) A real propose→approve loop: draft is surfaced with escalations, a reviewer
  approves or overrides, and every change is auditable (who / original → new /
  why) — the property a regulated workflow needs.
- (+) Resumable + persistent: a review can be reloaded (or resumed after a
  restart) via `thread_id`.
- (+) Clean seam for Phase 4c: the same override mechanism will host the
  IME-append feedback (promote a PT → re-fire seriousness criterion 6), and the
  escalation set is where precedent RAG (4d) will attach.
- (+) Verified: interrupt/resume + override-audit tests pass (API-free,
  MemorySaver); live E2E on case_003 (start 200 awaiting_review → GET 200 →
  approve applies an override + audit → double-approve 409, unknown 404, bad
  verdict 422). 41 tests pass.
- (−) State now carries Pydantic models through a checkpointer, needing the serde
  allow-list. Accepted (small, centralized in `dependencies`).
- (−) `auto_approve` is a second path through the review gate; kept minimal (one
  conditional) and covered by tests.

## Follow-up (2026-08-25, Phase 4f): reviewer can edit the extraction

The review now also edits the extraction, not just the verdicts: **remove** a
false-positive event, **re-code** its MedDRA PT (coded_by=手動), or **add** a missed
event with manually-supplied verdicts (default safe-side 要確認 / 否定できない). Chosen
"manual, no machine re-assessment" (the user's call) — added events get the
reviewer's verdicts, not a re-run of the pipeline; the graph does not loop. Applied
deterministically in `finalize` via `apply_extraction_edits` **before** the verdict
overrides (an override can target an added event), restructuring every aligned list
(extraction / meddra / seriousness / causality / expectedness) and dropping removed
terms from precedent + influence too. Non-destructive audit: `ReviewOutcome.
extraction_edits` (kind removed/added/recoded + detail). `ReviewDecision` gains
`removed_terms` / `added_events` / `recoded`; the router validates added-event
verdicts (422). Machine-assisted add (re-run the single-event pipeline) is deferred.
