# 0012 — Local generation A/B (per-step): no 7-8B preserves 過小0; hybrid is the path

- **Status:** Accepted
- **Date:** 2026-08-26
- **Phase:** 5 (cost × privacy × quality), slice 5b — generation
- **Evidence:** [per-step comparison](../../experiments/generation_comparison.md) (`experiments/scripts/generation_bench.py`) + wiring tests ([backend/tests/test_chat_provider.py](../../backend/tests/test_chat_provider.py))

## Context

Phase 5a put local *embeddings* behind the switch; 5b does the same for *generation*
and asks the real question: can a local model run the safety-critical judgment steps?
`chat_provider` + the per-step model factories were already the seam. `build_chat_model`
now dispatches openai | ollama; when ollama, every step runs on one
`settings.ollama_chat_model` (the "whole pipeline on one local model" mode).

**Benchmarking method — step isolation.** A full end-to-end triage on a local 7B is
impractical (~10-15 min/case: ~40 sequential structured-output calls). So each step is
benchmarked in isolation over the gold set — which is also exactly the per-step "where
does local hold vs break" question. Embeddings are held at OpenAI for every model, so
the A/B isolates generation. Reporting is **safety-weighted**: under-calls first.

**A hardening lesson (before any numbers).** Local structured output can *run away*
(constrained decoding loops) and hang; a Python-side timeout alone leaves the HTTP
request pending and wedges Ollama's queue. Fix baked into the production Ollama path:
`num_ctx=8192` (Ollama's 2048 default silently truncates a full ICSR + long prompt),
`num_predict=2048`, and a 120s client timeout — a truncated/failed call surfaces as an
error, not a hang.

## Findings

Candidates: OpenAI baseline (per-step 4o/mini) vs local qwen2.5:7b, ELYZA-JP-8B,
gemma3:4b, medllama2. Extraction recall is over all 23 gold events (5 cases); the
per-event steps over a 12-event subset (time). Single-run snapshot.

Total safety-critical under-calls (seriousness + causality + expectedness):

| model | 抽出 recall | MedDRA | 重篤度 過小 | 因果 過小 | 既知未知 | **総過小** | 失敗 |
|---|---|---|---|---|---|---|---|
| **openai** | 87% | 100% | **0** | **0** | 100% | **0** | 0 |
| ELYZA-JP-8B | **91%** | 100% | 2 | 0 | 50% | **2** | 0 |
| qwen2.5:7b | 61% | 75% | 3 | 0 | (12 hang) | **3** | 12 |
| gemma3:4b | 87% | 100% | 3 | 0 | 58% | **5** | 0 |
| medllama2 | 17% | 100% | 3 | 8 | 75% | **14** | 0 |

- **No local 7-8B preserves 過小0.** Every one under-calls on **seriousness** — the
  hard-narrative judgment (all four missed 徐脈（症候性）＝重篤). The safety invariant
  the pipeline holds with OpenAI is broken by every local model tested.
- **ELYZA-JP-8B is the clear best local** — JP tuning pays off: extraction 91% (beats
  OpenAI's 87%), cleanest names (English-leak 3, age 0), MedDRA 100%, causality 100%,
  fewest under-calls (2). Viable for extraction / coding / causality; still not safe on
  seriousness.
- **medllama2 is catastrophic** — English-medical Llama2: 17% extraction recall, 14
  under-calls, causality 33% (8 under-calls). A sharp lesson: a "medical LLM" whose
  language/base is wrong is *worse* than a general JP model, not better.
- **The conservative-default steps survive locally.** Causality under-calls stay 0 for
  the Llama3-family models because 否定できない is the default (ADR 0005) — the design
  protects the axis even when the model is weak. MedDRA is 100% for all but qwen because
  the exact-match path is deterministic and retrieval is held at OpenAI.
- **qwen uniquely hangs on expectedness** (12/12 fail); the other locals complete it.
- **Latency:** OpenAI 0.8-1.9s/step; locals 5-25s, up to 60s on hangs.

## Decision

Keep **OpenAI as the generation default**; local generation is an **opt-in with a
documented safety caveat** — at 7-8B it is **not a drop-in for the three judgment axes**
(seriousness / causality-on-hard-cases / expectedness). The honest cost×privacy answer
is **hybrid per-step**: a local model (ELYZA-JP-8B) is good enough for extraction,
MedDRA coding, and the conservative causality default; the safety-critical judgments
stay on the frontier model. This vindicates the per-step-selection architecture (ADR
0004/0005 split of LLM-interpret vs deterministic-decide is what lets the cheap steps
degrade gracefully).

Per-step *local* overrides (mix local + OpenAI in one run) are the natural next wiring
but are deferred — the benchmark first had to say which steps a local model may own.

## Consequences

- (+) A concrete, safety-weighted per-step map of where local generation holds vs
  breaks — the deliverable Phase 5b set out to produce, now reproducible for any new
  model (add one entry to `MODELS`).
- (+) Production Ollama path hardened (num_ctx / num_predict / timeout) so a local model
  cannot hang the pipeline.
- (+) The comparison harness is safety-first (under-calls surfaced per step) and
  resilient (per-call timeouts count hangs instead of stalling).
- (−) No local model is yet safe enough to reduce OpenAI dependence on the judgment
  axes, so the privacy/cost win from 5b is partial (embeddings are fully local per 5a;
  generation's easy steps could be, judgments not). Larger/instruct-tuned models
  (14B+, or a fine-tune on PV judgments) are the path to closing the seriousness gap.
- Scope/limits: single run, 12-event subset for per-event steps, small self-authored
  gold — the [EVALUATION](../../experiments/EVALUATION.md) caveats apply. 73 tests pass.
