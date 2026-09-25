# 0009 — Past-case precedent: structured per-(drug, PT) consistency (advisory)

- **Status:** Accepted
- **Date:** 2026-08-24
- **Phase:** 4 (orchestration), slice 4d-1
- **Evidence:** design + tests ([backend/tests/test_precedent.py](../../backend/tests/test_precedent.py)) + live E2E (draft surfaces precedent + consistency conflict; approval saved as precedent)

## Context

Phases 4b/4c let a reviewer approve, override, and grow the IME list, but each
review was blind to how *earlier* cases were decided. Cross-case **consistency**
is a core PV quality concern: the same event, under the same drug, should not be
judged 重篤 in one case and 非重篤 in the next without reason. Phase 4d ("precedent
RAG") surfaces prior decisions as context for the reviewer.

## Options

1. **Narrative vector RAG** — embed case narratives, retrieve top-k similar past
   cases. Good for "similar situation" context, but fuzzy for the actual question
   (was *this PT under this drug* serious?) and prone to retrieving a case about a
   different event — the dense-vector weakness on exact/variant matching we hit in
   ADR 0003.
2. **Structured per-(drug, PT) lookup** — index approved cases by (drug, pt_code)
   and report the past verdict distribution for the exact event. Precise and
   decision-relevant; matches everything else in the system (per-AE + PT).
3. **Let precedent adjust/suggest verdicts.** Rejected: it would blur the
   "LLM+deterministic decides, human reviews" separation and the audit trail.

## Decision

Adopt **option 2**, **advisory only** (both forks confirmed with the user:
structured lookup; auto-save approved cases + seed). Narrative RAG (option 1) is a
deferred follow-up (4d-2).

- **`PrecedentService`** indexes past cases by `(drug, pt_code)`. `summarize(...)`
  returns one `EventPrecedent` per adverse event: past verdict counts for
  seriousness / causality / expectedness, the contributing `case_ids`, and a
  **conflict** flag on seriousness/causality where the current draft verdict ≠ the
  precedent majority. seriousness/causality are event-level, so entries are
  **deduped by case** before counting (two matched drugs from one past case don't
  double-count); expectedness is per (drug, PT).
- **Advisory, never auto-changing a verdict.** Precedent is surfaced as its own
  draft section (⑦) and, on conflict, as an **escalation** ("今回: 非重篤／過去
  2件: 重篤2件") — the reviewer decides. This is the key contrast with the IME list
  (ADR 0008), which *does* fire criterion 6 deterministically; so precedent is
  **not** injected into a verdict's evidence.
- **Graph:** a new `precedent` node joins the three assessments (needs their
  verdicts + coded PTs) and feeds `human_review`:
  `[seriousness, causality, expectedness] → precedent → human_review → finalize`.
- **Store:** JSON records — a curated **seed** dir (`data/past_cases/`, tracked) +
  a **runtime** dir (`backend/past_cases/`, gitignored). On `approve`, the router
  saves the finalized case (`record_from_result`) and the singleton service
  refreshes its index, so a just-approved case is precedent for the next triage
  in-process (another feedback loop). Filenames key on `case_id` (overwrite
  dedupes).
- **Scope:** precedent uses the coded PT; events with no PT get no precedent.
  Conflict detection covers seriousness + causality in 4d-1 (single per-event
  verdicts); expectedness counts are shown but not conflict-flagged (per-drug,
  coarser — deferred).

## Consequences

- (+) Consistency signal at review time: "past approved cases judged this PT
  重篤 (2), you have 非重篤" is exactly the drift a first-pass triage should catch.
  Verified live on case_003: 鼻出血 → 過去2件 重篤, flagged against the 非重篤 draft;
  the approved case was then saved as new precedent.
- (+) Precise + auditable: exact PT match, named contributing `case_ids`, no
  vector fuzz. Advisory design keeps the verdict provenance clean.
- (+) Closes another loop: approvals accumulate as precedent (seed + runtime),
  shared as a singleton so it updates in-process.
- (−) Cold start: value grows with the corpus; seeds bootstrap it. Runtime store is
  single-node JSON (a DB is a later concern), and `case_id = document_name` so a
  re-approved filename overwrites its record.
- (−) No narrative-similarity retrieval yet (4d-2), and expectedness conflict is
  not flagged yet.
