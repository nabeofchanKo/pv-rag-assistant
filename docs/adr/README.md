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
| [0004](0004-seriousness-e2a-llm-plus-deterministic.md) | Seriousness (ICH E2A): LLM interprets criteria, a deterministic OR decides | Accepted | [criterion attribution](../../experiments/seriousness_attribution.md) |
| [0005](0005-causality-conservative-temporal.md) | Causality: conservative temporal triage (否定できない by default) | Accepted | [temporal causality](../../experiments/causality_temporal.md) |
| [0006](0006-langgraph-orchestration.md) | Triage orchestration via a workflow-type LangGraph StateGraph (fan-out DAG) | Accepted | design + parity tests |
| [0007](0007-hitl-approval-interrupt.md) | HITL approval via LangGraph interrupt/resume + SqliteSaver (propose→approve, audited) | Accepted | design + interrupt/resume tests + live E2E |
| [0008](0008-hitl-ime-promotion.md) | HITL that feeds accuracy: promote a PT to the IME list from a review (forward-looking) | Accepted | design + tests + live E2E |

Evidence for evidence-backed ADRs lives under [`experiments/`](../../experiments/),
with the reproducible script alongside each write-up.
