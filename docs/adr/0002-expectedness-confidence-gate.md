# 0002 — Expectedness confidence gate: match-type classification → deterministic verdict

- **Status:** Accepted
- **Date:** 2026-08-22
- **Phase:** 3, slice 3a
- **Evidence:** [experiments/expectedness_synonym_tolerance.md](../../experiments/expectedness_synonym_tolerance.md)

## Context

A plain 既知/未知 judgment ([ADR 0001](0001-expectedness-approach-a-rag.md)) turned
out to over-read 既知. A synonym-tolerance experiment on DrugX showed **all seven**
loosely-related terms returned 既知 — including a subtype mismatch (回転性めまい ↔
labelled 浮動性めまい) and a mechanism-only mention (血圧低下, appearing only as
"過度の血圧低下に伴い…"). For a first-pass screen the worst case is exactly this:
over-reading 既知 and **burying a genuinely unexpected, serious event with a short
reporting deadline**. We want to constrain "読み替え" (paraphrase/subtype) and
"機序・文脈のみ" (mechanism-only) matches without dropping them silently.

## Options considered

- **Numeric confidence + threshold.** LLM emits a 0–1 confidence; 既知 only above
  *n*. Faithful to the first instinct, but LLM self-confidence is poorly calibrated
  and *n* becomes a magic number.
- **Match-type classification + deterministic policy.** The LLM classifies only the
  *type* of match and cites the passage; a code-side policy table maps type → verdict.

## Decision

Adopt **match-type classification + deterministic policy**.

- The LLM returns `match_type ∈ {直接一致, 同義語, 読み替え・類似, 機序・文脈のみ, 該当なし}`
  plus the cited passage — never the verdict itself. Prompt instruction: *"迷ったら
  強い方（直接一致・同義語）に寄せない"* (bias to the safe band).
- Code maps type → a **4-value verdict**: 直接一致/同義語 → **既知**;
  読み替え・類似/機序・文脈のみ → **要確認**; 該当なし → **未知**; no passage → **判定不能**.
- `要確認` keeps its (possible-known) evidence for HITL but is **treated as not
  expected**. `ExpectednessAssessment.is_expected` is `True` **only for 既知**, so
  要確認/未知 never suppress expedited-reporting logic.

## Consequences

- (+) The two failure modes we named (subtype paraphrase, mechanism-only) land in
  要確認 with their evidence, escalated to a human rather than silently 既知. Verified:
  回転性めまい and 血圧低下 → 要確認; DrugZ case_003 unchanged (8/8).
- (+) Policy is a table (`_MATCH_TYPE_TO_VERDICT`) — auditable, unit-testable, and
  the knob for strictness — not a hidden float.
- (−) Residual LLM noise at the 同義語↔読み替え boundary (e.g. めまい → 要確認 though
  the word appears; 疲れ vs だるさ split). All errors stay in the safe 既知↔要確認
  band; nothing with a passage dropped to 未知.
- **Deferred:** tuning the boundary until after MedDRA coding, because the real fix
  is PT-level comparison (Vertigo ≠ Dizziness). The 要確認 layer is the hook the
  MedDRA AND-gate (mark 既知 only when term AND PT agree) will feed into.
