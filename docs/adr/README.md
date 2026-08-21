# Architecture Decision Records (ADR)

Short, durable records of the significant design decisions in this project — the
*why* behind non-obvious choices. Each ADR follows a light
[Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
format (Context / Options / Decision / Consequences) and links to the experiment
that produced its evidence, when there is one.

| # | Decision | Status | Evidence |
|---|----------|--------|----------|
| [0001](0001-expectedness-approach-a-rag.md) | Expectedness (既知/未知) via per-AE RAG over the label (Approach A) | Accepted | design |
| [0002](0002-expectedness-confidence-gate.md) | Confidence gate: match-type classification → deterministic verdict (既知/要確認/未知) | Accepted | [synonym tolerance](../../experiments/expectedness_synonym_tolerance.md) |
| [0003](0003-meddra-retrieval-hybrid.md) | MedDRA PT retrieval = hybrid BM25 (char-bigram) + vector, RRF-fused (Level B) | Accepted | [retrieval comparison](../../experiments/meddra_retrieval_comparison.md) |

Evidence for evidence-backed ADRs lives under [`experiments/`](../../experiments/),
with the reproducible script alongside each write-up.
