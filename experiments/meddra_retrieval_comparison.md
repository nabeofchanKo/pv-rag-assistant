# Experiment — MedDRA PT retrieval comparison

**Question:** which retrieval strategy best surfaces the correct MedDRA Preferred
Term for a Japanese adverse-event term? This drove [ADR 0003](../docs/adr/0003-meddra-retrieval-hybrid.md).

- **Date:** 2026-08-22
- **Reproduce:** `PYTHONPATH=backend python experiments/scripts/meddra_retrieval_compare.py`
  (needs `backend/.env` with `OPENAI_API_KEY`; makes live embedding calls)
- **Dictionary:** `data/meddra_sample/meddra_pt.csv` (56 PTs, Japanese `pt_name_ja`).
- **Strategies:** vector-only · Level A (normalized exact/substring + vector) ·
  Level B (BM25 char-bigram + vector, RRF-fused). Top-3 candidates each.

## Results (top-3 per strategy)

| AE term | expected PT | vector-only | Level A | **Level B (BM25+vec RRF)** |
|---|---|---|---|---|
| 頭痛 | 頭痛 | 頭痛 / 腹痛 / 胸痛 | 頭痛 / 腹痛 / 胸痛 | 頭痛 / 腹痛 / 頭痛… |
| 徐脈 | 徐脈 | 徐脈 / 頻脈 / 筋肉痛 | 徐脈 / 頻脈 / 筋肉痛 | 徐脈 / 頻脈 / 頭痛 |
| だるさ | 疲労 | ❌ うつ病 / 振戦 / 浮動性めまい | ❌ 同左 | △ 浮動性めまい / 疲労 / 腹痛 |
| 吐き気 | 悪心 | 嘔吐 / 悪心 / 便秘 | 嘔吐 / 悪心 / 便秘 | 嘔吐 / 悪心 / 腹痛 |
| 回転性めまい | 回転性めまい | 回転性めまい / … | 回転性めまい / … | 回転性めまい / … |
| 急性腎不全 | 急性腎障害 | 腎不全 / 急性腎障害 / … | 腎不全 / 急性腎障害 / … | 腎不全 / 急性腎障害 / … |
| **薬剤性肝障害** | 薬**物**性肝障害 | 薬物性肝障害 ✓ | ⚠️ **肝障害** / 薬物性肝障害 / … | ✅ **薬物性肝障害** / 肝障害 / … |
| **肝機能障害** | 肝機能**異常** | ⚠️ 肝障害 / 肝機能異常 / … | ⚠️ 肝障害 / 肝機能異常 / … | ✅ **肝機能異常** / 肝障害 / … |
| QT延長 | 心電図QT延長 | 心電図QT延長 / … | 心電図QT延長 / … | 心電図QT延長 / … |
| 血圧低下 | 低血圧 | 低血圧 / 高血圧 / 低血糖 | 低血圧 / 高血圧 / 低血糖 | 低血圧 / 高血圧 / 起立性低血圧 |

## Findings

1. **Exact matches** (頭痛, 徐脈, 回転性めまい): all three strategies rank the correct
   PT #1. Level A guarantees this deterministically rather than relying on embedding
   luck.
2. **Morphological variants** are the decisive cases and **Level B wins**:
   - `薬剤性肝障害 → 薬物性肝障害`: vector ✓, but **Level A over-promotes the shorter
     partial `肝障害`**; Level B ranks the correct PT #1.
   - `肝機能障害 → 肝機能異常`: vector and Level A rank `肝障害` first; **Level B ranks
     `肝機能異常` #1**.
3. **Colloquial, zero lexical overlap** (`だるさ → 疲労`): weak for *all* strategies
   (vector misses 疲労 in top-3). Level B's `疲労` hit is partly a BM25 all-zero →
   CSV-order artifact, **not a robust signal**. This case needs dictionary aliases +
   the LLM selector, not retrieval tuning.

## Decision

Adopt **Level B** (see ADR 0003). Character-bigram BM25 avoids a Japanese
morphological-analyser dependency; BM25 + RRF are implemented inline. On this small
sample the practical gain over "Level A + LLM" is modest but grows with dictionary
scale, and it delivers the README "hybrid retrieval" roadmap item.
