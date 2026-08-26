# 0011 — Local embedding provider (Ollama / bge-m3) behind the provider switch

- **Status:** Accepted
- **Date:** 2026-08-26
- **Phase:** 5 (cost × privacy × quality), slice 5a — embeddings
- **Evidence:** [retrieval bench](../../experiments/embedding_retrieval_bench.md) (`experiments/scripts/embedding_retrieval_bench.py`, LLM-free) + an end-to-end safety-regression run + wiring tests ([backend/tests/test_embedding_provider.py](../../backend/tests/test_embedding_provider.py))

## Context

The whole pipeline embeds through OpenAI `text-embedding-3-small`, so every case
narrative and drug-label passage leaves the machine. Phase 5's goal is to offer a
PV shop an **on-prem/local tier** (privacy) and a cheaper tier, benchmarked
honestly rather than assumed. The seam was already in place: `config.py` carries an
`embedding_provider` switch and `dependencies.get_embeddings()` is the single
factory every retriever draws from.

Two things made "local embeddings" the right first slice: it is a **one-factory
change** (unlike generation's seven per-step models), and the privacy argument is
sharpest for embeddings (the case text is exactly what you least want to send to a
cloud API). Mid-slice the OpenAI account **ran out of credits** (HTTP 429
`insufficient_quota`), which turned the local option from a comparison into a
concrete operational need.

## Options

1. **sentence-transformers / HuggingFace, in-process.** Most control, and models
   not in Ollama are reachable. But this machine's GPU is an RTX 5070 (Blackwell,
   sm_120): a working CUDA `torch` needs a very recent (12.8+) build, which is real
   setup friction, and it makes the venv heavy.
2. **Ollama as the local runtime.** Already installed (0.17.1); **bundles its own
   CUDA runtime**, so no `torch` in the venv and the Blackwell problem disappears.
   Exposes an OpenAI-compatible server; `langchain-ollama` slots straight behind the
   factory. Model choice is limited to what Ollama serves (fine for bge-m3 / Ruri /
   the JP generation candidates).

For the embedding model itself: **BGE-M3** (multilingual, 1024-dim, strong on
Japanese, widely benchmarked) as the first local pick; Ruri (`cl-nagoya/ruri-*`)
is a later A/B point.

## Decision

Adopt **option 2** (confirmed with the user: runtime = Ollama; start with bge-m3).

- **`get_embeddings()` dispatches on `settings.embedding_provider`** — `openai`
  (default) or `ollama` (lazy `import langchain_ollama` so the dep is only required
  when selected). Unknown provider → `ValueError`.
- **Provider-scoped Chroma dir.** A collection is bound to one embedding dimension
  (OpenAI 1536, bge-m3 1024), so `Settings.chroma_dir` nests the store under an
  `embedding_id` (`openai__text-embedding-3-small`, `ollama__bge-m3`). Both
  providers coexist on disk, the A/B is a flag flip, and the startup lifespan
  re-indexes the reference collections (`drug_labels`, `meddra_pt`) into an empty
  dir automatically. It lives under the gitignored `chroma_db/`.
- **OpenAI stays the default**, bge-m3 is a **validated opt-in**
  (`EMBEDDING_PROVIDER=ollama`) — an honest "cloud default, local option" posture,
  and it keeps local's per-run index/latency cost off the default path.
- The eval harness gained a `TRIAGE_EVAL_OUT` override so a provider A/B run writes
  to its own file instead of clobbering the canonical baseline report.

## Evidence

**Retrieval bench (LLM-free, deterministic).** For every in-scope gold event term
(23; 13 exact-matchable, **10 hard = no exact dictionary hit**), does the correct
MedDRA PT land in the top-k — via `hybrid` (exact ⊕ char-bigram BM25 ⊕ vector) and
via `vector` alone? Repro:
`./venv/Scripts/python.exe experiments/scripts/embedding_retrieval_bench.py`.

| | OpenAI 1536 | bge-m3 1024 |
|---|---|---|
| hybrid@3 (all 23) | 100% | **100%** |
| vector-only@1 (all) | 100% (23/23) | 96% (22/23) |
| vector-only@1 (hard, n=10) | 100% (10/10) | 90% (9/10) |
| hybrid@3 (hard) | 100% | **100%** |
| query search, warm | 189 ms | 260 ms |
| index build (56 PT) | 1.6 s | 7.8 s |

**End-to-end safety-regression** (embeddings=bge-m3, generation still OpenAI):
`EMBEDDING_PROVIDER=ollama TRIAGE_EVAL_OUT=experiments/triage_eval_bge-m3.md
./venv/Scripts/python.exe experiments/scripts/triage_eval.py` → MedDRA **23/23**,
under-call **0/0/0** (seriousness/causality/expectedness, both influence modes),
A/B safe-side↑1 / downgrade **0** — identical to the OpenAI-embedding baseline, and
it exercises drug-label retrieval (which the retrieval bench does not).

## Consequences

- (+) **Quality parity at the system level.** The only measurable gap is one term
  at vector-only **rank-1**; it is absorbed by the exact+BM25 fusion and gone by
  rank-3, so the `hybrid` retrieval the system actually uses is identical (100%@3).
  The hybrid design (ADR 0003) is what makes a local embedding safe to drop in —
  lexical signals carry the case when the dense vector is marginally weaker.
- (+) **The safety invariant holds end-to-end** under local embeddings (過小0),
  expectedness (label retrieval) included.
- (+) **On-prem privacy + zero marginal cost + no quota** — the actual win. When the
  OpenAI credits ran out, `EMBEDDING_PROVIDER=ollama` still runs, fully local.
- (−) **Local is not faster here.** Per-query latency and index build are both
  slower than OpenAI, largely because LangChain's `OllamaEmbeddings` embeds
  documents **one at a time** (sequential HTTP), not the raw model speed. Local's
  case is privacy/cost, not speed. A batched embedder or `embed_documents`
  concurrency is a later optimization.
- (−) Switching providers means re-indexing every collection into a new
  provider-scoped dir (automatic at startup, but a cold cost). Small at this scale.
- Scope: embeddings only. Generation stays OpenAI (slice 5b will A/B local chat
  models per step). 69 tests pass (+4 wiring/scoping). Numbers are a single-run
  snapshot on a small self-authored gold — the [EVALUATION](../../experiments/EVALUATION.md)
  limits apply.
