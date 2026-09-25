# 0010 — Past-data influence mode (applied / advisory), via an influence layer

- **Status:** Accepted
- **Date:** 2026-08-24
- **Phase:** 4 (orchestration), slice 4e
- **Evidence:** design + tests ([backend/tests/test_influence.py](../../backend/tests/test_influence.py)) + live A/B (same case, applied vs advisory)

## Context

By Phase 4d the system used two kinds of past data, but **inconsistently**: past
*feedback* (an IME promotion) fired E2A criterion 6 **deterministically** (baked
into the verdict), while past *cases* (precedent) were **advisory** (shown, never
applied). A user asked for a single ON/OFF so the two behaviors can be compared —
"decide using accumulated history" vs "decide fresh, history as a footnote" —
useful for evaluation and for a reviewer to see the delta.

## Options

1. **Thread a flag through each assessment service.** Small change, but the
   "fresh judgment" is never isolated (IME still lives inside seriousness), so the
   comparison is muddier and the past-data logic stays scattered.
2. **An influence layer.** Assessment services always produce the **fresh**
   verdict (current case only); a dedicated node folds past data in (applied) or
   annotates (advisory). Advisory output == fresh, so the A/B is exact and every
   history effect is in one auditable place.

## Decision

Adopt **option 2** (confirmed with the user: clean influence layer; safe-side
nudge only for precedent; default = applied).

- **Move IME out of `SeriousnessService`** → seriousness is now fresh-only
  (LLM criteria + deterministic OR). IME criterion 6 application moves to the
  influence layer (see ADR 0004 follow-up).
- **`InfluenceService.apply(mode, …)`** runs as the `influence` graph node, after
  `precedent`, before `human_review`:
  `[seriousness, causality, expectedness] → precedent → influence → human_review`.
- **applied (default)** — history is authoritative, but asymmetrically by source:
  - **IME** (explicit prior human decision) → criterion 6 = **重篤**
    deterministically, citing the PT + provenance.
  - **precedent** (aggregate statistics) → **safe-side nudge only**: if the past
    majority is stricter than the fresh verdict, raise it — but **only to 要確認**
    (surface for the human, never auto-重篤), and **never a downgrade**. Causality:
    a fresh 否定できる against a past in-scope majority → 否定できない.
- **advisory** — verdicts unchanged; the same signals become notes
  ("以前のFB(IME昇格)では…", "過去症例では 重篤2件").
- Every effect is an `InfluenceItem{axis, term, source, applied, from→to, note}`.
- **Per-request toggle** `POST /cases/triage?influence=applied|advisory` (default
  applied) + a Streamlit switch, so the same case can be run both ways.
- **Scope:** seriousness (IME + precedent) and causality (precedent). Expectedness
  influence added in a follow-up (see below).

### Follow-up (2026-08-25): expectedness (既知/未知) now covered

Precedent conflict + influence now include expectedness, closing the last judgment
axis. Reporting severity: 既知(0) < 要確認 < 判定不能 < 未知(2) (未知 = unexpected →
expedited). applied nudges a fresh **既知 → 要確認** only when the past majority is
stricter, per (drug, PT); **never a downgrade** (未知 stays), capped at 要確認 (not
auto-未知). advisory adds an expectedness note. Precedent expectedness is
drug-agnostic-aggregated in `EventPrecedent`, and a conflict fires only when the
case actually assessed that term's expectedness — fine while the own-company
suspect drug is singular per case (a per-drug precedent index is a later refinement).

## Consequences

- (+) A clean, honest A/B: advisory == the model's fresh judgment; applied == the
  system's history-adjusted judgment. Verified live on case_003 — 鼻出血: applied
  → 要確認 (fresh 非重篤 nudged by past 重篤×2, "→安全側で要確認"); advisory →
  非重篤 kept, with the precedent shown as a note.
- (+) Safety preserved: precedent only ever escalates (to 要確認) and never
  downgrades, so accumulated history can't cause under-reporting.
- (+) All past-data effects are consolidated + auditable in one layer; the two
  sources keep their distinct semantics (IME authoritative, precedent cautious).
- (+) 55 tests pass; the fresh/influence split let the assessment suites simplify.
- (−) Seriousness no longer self-applies IME (ADR 0004 change); mitigated by moving
  its tests to the influence suite. Advisory mode still runs the same LLM calls
  (no cost saving) — it isolates *influence*, not compute.
