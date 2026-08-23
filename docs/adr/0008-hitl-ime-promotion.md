# 0008 — HITL that feeds accuracy: IME promotion from a review

- **Status:** Accepted
- **Date:** 2026-08-24
- **Phase:** 4 (orchestration), slice 4c
- **Evidence:** design + tests ([backend/tests/test_ime.py](../../backend/tests/test_ime.py)) + live E2E (promote during approval → live IME set grows, tracked CSV untouched)

## Context

Phase 4b gave the reviewer a real approve/override gate (ADR 0007), but the
corrections stayed local to one case. The point of HITL in this project is that a
reviewer's judgment should **improve later accuracy**, not just fix the case in
hand. The hook already existed: seriousness criterion 6 (医学的に重要) fires
deterministically when an event's coded MedDRA PT is on the IME list, and that
list was designed to be appended to (ADR 0004). Phase 4c wires the append to the
review.

## Options

1. **Promote via a separate reference-admin endpoint only.** Clean separation but
   decouples "I judged this medically important" from "grow the list" into two
   disconnected steps — the reviewer rarely comes back to do the second.
2. **Re-run the whole case (and siblings) when a PT is promoted.** Maximizes
   intra-case consistency but means re-executing seriousness mid-review and
   rewriting an assessment the reviewer is in the middle of — complex, and it
   muddies "the approved record is what the human signed off".
3. **Promote inside the approval, forward-looking.** The reviewer promotes a PT as
   part of `approve`; the list grows for *future* cases; the current event is
   handled by the reviewer's explicit override.

## Decision

Adopt **option 3** (both design forks confirmed with the user: promote-in-review;
forward-looking only).

- **`ImeReference.promote(pt_code, pt_name, note)`** — idempotent (`追加` vs `既存`,
  no duplicate row), thread-locked; updates the **in-memory set AND appends the
  CSV**. The `ImeReference` is a DI singleton shared with `SeriousnessService`, so
  a promotion is visible to the **next assessment in the same process** — no
  restart. The `note` records `HITL昇格 <reviewer> <date> — <rationale>`.
- **Where:** the promotion is a **reference-side effect performed in the router**
  (`/approve`, on `approve` only), then its resolved `ImePromotionRecord`s are
  threaded into the resume payload so `finalize` records them in the audit trail
  (`ReviewOutcome.ime_promotions`) — one consistent audit object, and the graph
  stays free of filesystem side effects.
- **Scope = forward-looking.** The current event's verdict comes from the
  reviewer's override; finalized cases are immutable records and are **not**
  retroactively re-assessed. Promotion only changes behavior for later cases.
- **Schemas:** input `ImePromotion{pt_code, pt_name, rationale}` on
  `ReviewDecision.ime_promotions`; audit `ImePromotionRecord{…, promoted_at,
  status}` on `ReviewOutcome.ime_promotions`. The router validates a real
  `pt_code` is present (422 otherwise) — only coded events can key criterion 6.
- **UI:** the review form lists events that have a coded PT with an "IMEに追加"
  checkbox + rationale; approving promotes the checked PTs and the finalized view
  shows what was promoted.

## Consequences

- (+) The loop closes: an approval measurably changes the machine's later output.
  Verified live — promoting 鼻出血 (PT 10015090) during a case_003 approval flipped
  the running server's IME membership to true, so a subsequent case with that PT
  would auto-fire criterion 6; the tracked `ime_pt.csv` was untouched (temp copy).
- (+) Auditable both ways: per-case (`ReviewOutcome.ime_promotions`) and in the
  reference itself (CSV `note` with reviewer + date).
- (+) Deterministic payoff test (no LLM): promote a PT → the next seriousness
  assessment of an event coded to it returns 重篤 via an IME hit. 46 tests pass.
- (−) The IME CSV is a shared mutable file; concurrent promotes are serialized by a
  lock, but this is single-node (fine for the current scope; a DB-backed store is a
  later concern).
- (−) No de-promotion / review-of-the-list flow yet (a promoted PT stays). Adding a
  reference-admin surface (option 1, as a *complement*) is deferred.
