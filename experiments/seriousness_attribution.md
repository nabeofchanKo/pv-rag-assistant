# Experiment — seriousness criterion attribution

**Question:** does the seriousness assessor attribute the ICH E2A criteria to the
*right* adverse event, and handle euphemisms, without borrowing another event's
hospitalization? Drove the model + prompt decisions in [ADR 0004](../docs/adr/0004-seriousness-e2a-llm-plus-deterministic.md).

- **Date:** 2026-08-22
- **Reproduce:** `PYTHONPATH=backend python experiments/scripts/seriousness_attribution.py`
  (needs `backend/.env` with `OPENAI_API_KEY`; makes live calls)
- **Targets:** case_001 (no hospitalization; 頭痛 is *severe* but non-serious) and
  case_003 (hospitalization for 徐脈/失神; other events non-serious).

## Before — gpt-4o-mini, loose prompt (WRONG)

| case | event | reported | assessed | problem |
|---|---|---|---|---|
| 001 | 頭痛 / めまい / 悪心 | 非重篤 | 要確認 [入院] | 疑い emitted from *negative* text ("対症療法を要さなかった") |
| 003 | INR増加 / 斑状出血 | 非重篤 | 重篤 [入院] | borrowed 徐脈/失神's hospitalization |
| 003 | 鼻出血 | 非重篤 | 重篤 [入院] | 外来受診 miscounted as hospitalization |

Over-attribution across events + flagging from absence of evidence.

## Fix

1. **Prompt hardening** — only positive evidence attributable to *this* event;
   外来受診/対症療法/投与中止 ≠ hospitalization; do not borrow another event's admission;
   an event arising *during* an admission is not serious by that admission.
2. **Model → gpt-4o** — hospitalization attribution is the hard-narrative class where
   mini leaked in extraction too (per-step model selection).

## After — gpt-4o, hardened prompt (CORRECT, one accepted residual)

| case | event | reported | assessed | criterion |
|---|---|---|---|---|
| 001 | 頭痛（重度）/ めまい / 悪心 | 非重篤 | ⚪ 非重篤 | — (severity ≠ seriousness) |
| 003 | INR増加 / 鼻出血 / 斑状出血 | 非重篤 | ⚪ 非重篤 | — (no borrowed admission) |
| 003 | 徐脈 / 失神 | 重篤 | 🔴 重篤 | 入院 ✓ |
| 003 | 起立性低血圧 | 非重篤 | 🔴 重篤 | 入院 — **accepted residual** |
| 003 | 錯乱状態 / 浮動性めまい | 非重篤 | ⚪ 非重篤 | — |

## Accepted residual

起立性低血圧 arose *during* the admission (for 徐脈/失神) and resolved by discharge, so
by E2A it is not serious-by-hospitalization; the model still calls it 重篤[入院]. Accepted
as a **safe-side over-call** surfaced as a reporter-vs-company ⚠️差異 for HITL (better than
an under-call). See ADR 0004.
