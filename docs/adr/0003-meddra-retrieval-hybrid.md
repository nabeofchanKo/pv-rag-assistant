# 0003 — MedDRA PT retrieval = hybrid BM25 (char-bigram) + vector, RRF-fused

- **Status:** Accepted
- **Date:** 2026-08-22
- **Phase:** 3 (MedDRA term suggestion)
- **Evidence:** [experiments/meddra_retrieval_comparison.md](../../experiments/meddra_retrieval_comparison.md)

## Context

MedDRA coding suggests a Preferred Term (PT) for each extracted (Japanese) adverse
event. The dictionary was localised to Japanese (`pt_name_ja`) so matching is
same-language. Retrieval feeds candidate PTs to an LLM selector — but a controlled
terminology is dominated by *exact and near-exact* matches, and dense-vector search
is known to be weak on exact/lexical matches and morphological variants (also noted
in the README's known limitations). How should candidates be retrieved?

## Options considered

Measured on 10 representative terms (exact, colloquial, morphological variants):

- **Vector-only.** Drifts on variants — e.g. `肝機能障害` ranked `肝障害` above the
  correct `肝機能異常`; missed `疲労` for `だるさ` entirely (top-3).
- **Level A — normalized exact/substring + vector.** Deterministic exact match is
  solid, but naive substring **over-promotes a shorter partial**: `薬剤性肝障害`
  ranked `肝障害` above the correct `薬物性肝障害`.
- **Level B — BM25 (character-bigram) + vector, fused with Reciprocal Rank Fusion.**
  Ranked the correct variant PT #1 on both hard cases (`薬剤性肝障害 → 薬物性肝障害`,
  `肝機能障害 → 肝機能異常`).

## Decision

Adopt **Level B**: BM25 over **character bigrams** (so no Japanese morphological
analyser / MeCab dependency) fused with the dense-vector ranking via RRF, plus a
normalized-exact-match fast path; the LLM then selects from the fused candidates.
BM25 + RRF are implemented **inline** (no new library) to stay light and auditable.

## Consequences

- (+) Best on the morphological variants that MedDRA coding actually needs help with,
  and keeps exact matches rank-1.
- (+) Delivers the README roadmap "hybrid retrieval" item; character-bigram BM25
  avoids a heavy JA-tokenizer dependency.
- (−) Colloquial terms with no lexical overlap (`だるさ → 疲労`) remain weak for *all*
  retrievers — to be handled by dictionary **aliases + the LLM selector**, not by
  retrieval alone. (In the experiment, Level B's `疲労` hit was partly a BM25
  all-zero → CSV-order artifact, not a robust signal — recorded honestly.)
- On this ~56-row sample the practical gain over "Level A + LLM" is modest; it grows
  with dictionary scale.
