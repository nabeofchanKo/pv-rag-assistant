# 0004 — Company seriousness (ICH E2A): LLM interprets, a deterministic rule decides

- **Status:** Accepted
- **Date:** 2026-08-22
- **Phase:** 3 (seriousness assessment), slice 3c
- **Evidence:** [experiments/seriousness_attribution.md](../../experiments/seriousness_attribution.md)

## Context

`seriousness_assessed` is the **company** seriousness (ICH E2A), kept distinct from
the reporter's transcribed `seriousness_reported` so the two can be compared (a
reporter's 非重篤 can be company 重篤, e.g. hospitalization occurred). The naive
"hybrid = keyword-match criteria 1–5, LLM for criterion 6" fails: euphemisms
(「逝去された」=death, 「退院を予定していたが未定となった」=prolonged hospitalization)
would be missed by keyword matching — an under-reporting risk, the worst case.

## Decision

Split by **role**, not by criterion:

- **LLM interprets language** — reads the case text for the given event and flags
  which E2A criteria are met (status 該当/疑い) with an evidence quote. This catches
  euphemistic phrasings that keyword matching cannot.
- **A deterministic rule decides the verdict** — E2A is a logical OR (any criterion
  → serious), which is where auditability belongs: any 該当 → 重篤; only 疑い → 要確認
  (safe side, HITL); none → 非重篤. `is_serious` is True only for 重篤, so 要確認/非重篤
  never suppress reporting.
- **Criterion 6 (医学的に重要)** also fires deterministically when the event's coded
  MedDRA PT is on the **IME list** (drug-independent, PT-keyed, **HITL-appendable** —
  a reviewer's criterion-6 decision can promote a PT), OR from the LLM's contextual read.

## The attribution lesson (why gpt-4o + a hardened prompt)

First verification exposed **over-attribution**: with gpt-4o-mini and a loose prompt,
the hospitalization criterion was borrowed across events (INR増加/鼻出血/斑状出血 marked
重篤 from the hospitalization that belonged to 徐脈/失神), and 疑い was emitted from
*negative* text ("対症療法を要さなかった"). Fixed by:

- prompt hardening — flag a criterion only from **positive** evidence attributable to
  *this* event; 外来受診/対症療法/投与中止 are not hospitalization; do not borrow another
  event's admission; an event merely arising *during* an admission is not serious;
- **model bump to gpt-4o** — attribution is the hard-narrative class where mini leaked
  in extraction too (per-step model selection; `openai_seriousness_model`).

After the fix: case_001 all 非重篤 (incl. 頭痛(重度) → 非重篤, severity≠seriousness);
case_003 correct except one accepted residual.

## Consequences

- (+) Euphemisms handled by the LLM; the serious/non decision is a traceable rule
  (which criterion + which quote). Reporter-vs-company divergence is surfaced.
- (−) **Accepted residual:** an event arising *during* an admission for other events
  (起立性低血圧) is still over-called 重篤[入院]. Accepted as a **safe-side over-call**
  surfaced as a reporter-vs-company ⚠️差異 for HITL, rather than risking an under-call
  (user decision, consistent with ADR 0002's safe-side philosophy).
- IME + 要確認 are the hooks the HITL/precedent loop (Phase 4) will grow into.
