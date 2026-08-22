# Experiment — conservative temporal causality

**Question:** does the conservative rule keep post-administration events in scope
(否定できない) and exclude only clear temporal incompatibilities — while respecting
residual/delayed effects for post-discontinuation onsets? Drove [ADR 0005](../docs/adr/0005-causality-conservative-temporal.md).

- **Date:** 2026-08-22
- **Reproduce:** `PYTHONPATH=backend python experiments/scripts/causality_temporal.py`
  (needs `backend/.env` with `OPENAI_API_KEY`; makes live calls)
- **Target:** case_003 (DrugZ start 2025-09-10; stopped ~2025-11-27 per narrative).

## Results (case_003)

| event | onset | onset_relation | verdict |
|---|---|---|---|
| INR増加 | 2025-10-12 | 投与中 | 🔴 否定できない |
| 鼻出血 | 2025-10-14 | 投与中 | 🔴 否定できない |
| 斑状出血 | 2025-10-15 | 投与中 | 🔴 否定できない |
| 徐脈 | 2025-11-22 | 投与中 | 🔴 否定できない |
| 失神 | 2025-11-22 | 投与中 | 🔴 否定できない |
| 起立性低血圧 | 2025-11-23 | 投与中 | 🔴 否定できない |
| 錯乱状態 | 2025-12-15 | 投与中止後 | 🔴 否定できない |
| 浮動性めまい | 2025-12-15 | 投与中止後 | 🔴 否定できない |

## Findings

- All during-treatment events → 否定できない (the conservative default; stays in scope).
- **The two post-discontinuation events (onset ~3 weeks after stopping DrugZ) stayed
  否定できない**, not excluded — the model set `clearly_excludable = false` citing the
  narrative's own reasoning: "DrugZは消失半減期が長く（活性代謝物で数週間と推定される）、
  遅発性の中枢神経系への影響は否定できなかった". This is exactly the residual-effect nuance
  chosen for the post-discontinuation branch.
- No case in the sample data has an onset *before* administration, so 否定できる is exercised
  only in the unit tests; the live behaviour on real cases is the conservative default,
  as intended.
