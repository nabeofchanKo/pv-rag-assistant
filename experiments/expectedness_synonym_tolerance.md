# Experiment — expectedness synonym tolerance

**Question:** how far can a reported/narrative adverse-event term differ from the
package-insert wording and still be judged 既知? This drove the confidence gate in
[ADR 0002](../docs/adr/0002-expectedness-confidence-gate.md).

- **Date:** 2026-08-22
- **Reproduce:** `PYTHONPATH=backend python experiments/scripts/expectedness_synonym_tolerance.py`
  (needs `backend/.env` with `OPENAI_API_KEY`; makes live calls)
- **Target:** DrugX (`data/drug_labels/drugx_label.md`), 7 deliberately-varied terms.

## Before the gate (plain 既知/未知)

Every term came back **既知** — the model generalised across paraphrase, colloquial
wording, generic↔specific, subtype differences, and even a mechanism-only mention:

| term | verdict | matched label wording | difference |
|---|---|---|---|
| めまい | 既知 | 「…立ちくらみ、めまい等…」(8.) | near-identical |
| 回転性めまい | 既知 | 「浮動性めまい」(11.2) | **subtype** (vertigo ≠ dizziness) |
| 顔のほてり感 | 既知 | 「ほてり（顔面潮紅）」(11.2) | paraphrase |
| 疲れ | 既知 | 「倦怠感」(11.2) | colloquial |
| 浮腫 | 既知 | 「血管浮腫」(11.1) | generic↔specific |
| だるさ | 既知 | 「倦怠感」(11.2) | colloquial |
| 血圧低下 | 既知 | 「過度の血圧低下による…」(8.) | **mechanism/context only** |

The worst case for a first-pass screen is over-reading 既知 and burying a genuinely
unexpected, serious event. The two risky patterns are the **subtype** (回転性めまい)
and **mechanism-only** (血圧低下) rows.

## After the gate (match-type → 既知/要確認/未知)

| term | verdict | match_type |
|---|---|---|
| めまい | 🟡 要確認 | 読み替え・類似 |
| **回転性めまい** | 🟡 **要確認** | 読み替え・類似 |
| 顔のほてり感 | 🟢 既知 | 同義語 |
| 疲れ | 🟡 要確認 | 読み替え・類似 |
| 浮腫 | 🟢 既知 | 同義語 |
| だるさ | 🟢 既知 | 同義語 |
| **血圧低下** | 🟡 **要確認** | 機序・文脈のみ |

The two named patterns now land in **要確認** (`is_expected = False`, evidence kept
for HITL). Regression check on DrugZ / case_003 was **8/8 unchanged**.

## Honest residual

Boundary noise remains between 同義語 and 読み替え (めまい → 要確認 although the word
appears; 疲れ vs だるさ split; 浮腫 → 既知). **All errors stay in the safe 既知↔要確認
band** — nothing with a supporting passage dropped to 未知. Tuning is deferred until
MedDRA PT-level comparison exists (the real fix); see ADR 0002.
