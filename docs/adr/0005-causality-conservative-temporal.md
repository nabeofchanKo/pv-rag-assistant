# 0005 — Causality (因果関係): conservative temporal triage, not a causality proof

- **Status:** Accepted
- **Date:** 2026-08-22
- **Phase:** 3 (causality), slice 3d
- **Evidence:** [experiments/causality_temporal.md](../../experiments/causality_temporal.md)

## Context

The last Phase 3 evaluation task. For a first-pass triage we do **not** try to prove
causality (no full dechallenge/rechallenge/exposure argument). The user's directive:
an event that occurred **after** the suspect drug's administration defaults to
「否定できない」(cannot be ruled out — stays in scope); conclude 「否定できる」(can be
ruled out) **only** on a *clear* temporal incompatibility — onset before
administration, or onset after discontinuation **when residual/delayed effects are
also implausible**. Err toward keeping events in scope (don't under-report).

## Decision

Split by role (as in ADR 0004): the LLM classifies the temporal relationship and
cites evidence; a deterministic rule maps it to the verdict, holding the conservative
default.

- LLM output: `onset_relation ∈ {投与開始前, 投与中, 投与中止後, 不明}` +
  `clearly_excludable` (meaningful only for 投与中止後 — true only when residual /
  delayed effects, e.g. a long half-life, are also implausible) + evidence quote.
- Deterministic rule (`_verdict`):
  - 投与開始前 → **否定できる**
  - 投与中止後 **and** clearly_excludable → **否定できる**
  - 投与中, or 投与中止後 without clear incompatibility → **否定できない** (default)
  - 不明 → **評価不能**
- `is_excludable` is True only for 否定できる; 否定できない / 評価不能 both stay in scope.
  Model = gpt-4o (temporal + narrative reasoning; per-step selection, as for seriousness).

## Consequences

- (+) Conservative: real cases default to 否定できない (kept in scope). Verified 8/8 on
  case_003 — every during-treatment event → 否定できない; the two post-discontinuation
  events (錯乱状態, 浮動性めまい, onset 3 weeks after stopping DrugZ) correctly stayed
  否定できない because the narrative notes a long half-life / delayed CNS effect — the
  residual-effect nuance the user chose.
- (+) 評価不能 (dates insufficient) is treated as *not excluded* — still in scope.
- (−) By design this never asserts positive causality — that is out of scope for triage.
- Onset dates come from extraction as a hint, but the LLM re-reads the case text for the
  administration timeline, so drug administration dates need not be separately structured.
