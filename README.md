# PV Triage Assistant

**A first-pass assessment assistant for pharmacovigilance (PV): it reads an adverse event report and drafts seriousness, expectedness and causality with the evidence behind each verdict, for a human to approve.**

🌐 **English** ｜ [日本語](README.ja.md)

**Live demo:** [English](https://h4b6m4zyqj.ap-northeast-1.awsapprunner.com/en/triage) ・ [日本語](https://h4b6m4zyqj.ap-northeast-1.awsapprunner.com/ja/triage) ・ [Case study](https://h4b6m4zyqj.ap-northeast-1.awsapprunner.com/en/about) (the problem, the decisions, what the evaluation does and doesn't show)

No sign-up. The public demo runs the real pipeline on bundled synthetic cases (or one you compose in the case builder), is rate limited, and accepts no uploads — it calls a paid LLM API.

---

## Why

A safety team has to decide, for every incoming report, whether it is serious, whether the reaction is already in the label, and whether a causal link can be ruled out — then report within a deadline. The domain is asymmetric: **an over-call costs review time; an under-call is a missed report.** So this project treats three things as design constraints rather than features:

- **Never under-call.** Uncertain judgments land on the conservative side (要確認 / 否定できない) and are surfaced for a human, not silently resolved.
- **Every verdict has a source.** The quoted case text, the ICH E2A criterion met, or the package-insert passage matched.
- **A human decides.** The system drafts; a reviewer approves, and every change keeps the original as an audit trail.

The domain comes from my own PV background (adverse event assessment, bilingual JP/EN regulatory documentation). It is a portfolio piece built so that I can explain every design choice in it.

## What it does

1. **Triage a case** (PDF, text, email or scanned image) — own-product gate → extraction of patient and adverse events, *including events that appear only in the narrative* → MedDRA PT coding → seriousness (ICH E2A), expectedness (against the package insert) and temporal causality, in parallel → consistency with past approved cases.
2. **Review and approve** — the run pauses for a reviewer, who can override any verdict, correct the extraction, or promote a PT to the medically-important-events list. Approved cases become precedent for later ones.
3. **Show its cost** — every run reports its measured tokens, USD cost and time per step (a sample case: about **$0.03–0.04 and 15–18 s**).
4. **Ask (RAG Q&A)** — index a report and ask about it, with cited passages. This was the project's starting point.

## Evaluation

Scored against a hand-built gold set of synthetic cases, safety-weighted (under-calls first). Full write-up: [experiments/EVALUATION.md](experiments/EVALUATION.md).

| | Result |
|---|---|
| **Under-calls** (seriousness, causality, expectedness) | **0** — in the main run, across 3 repeated runs, on held-out cases and on the hard cases |
| MedDRA PT coding | **100%** (23/23) — a single-LLM baseline scores 29% |
| Expectedness | **100%** — the single-LLM baseline under-calls 3 times; the pipeline 0 |
| Seriousness | **83–91%** across the evaluation runs (main 83–87%, repeated 87–90%, baseline comparison 91%) — every miss is a safe-side over-call |
| Own-product gate | 2/2 out-of-scope cases stopped before any assessment |

**What this does not show:** the sample is small (7 synthetic cases; 5 in scope, 23 events), and the gold set was drafted with an LLM and corrected by a PV expert, not independently double-annotated. "Past-case feedback improves accuracy" was **not** demonstrated: on held-out cases precedent changed nothing, and the one earlier improvement was traced to seed data. A single LLM call is competitive on seriousness and causality; the pipeline's measured advantage is in MedDRA coding and expectedness, and in never under-calling.

## Architecture

```
case report (PDF / text / email / image) ── ingestion: pdfplumber + NFKC, .eml, OCR
    │
    ▼
product_match ──── no own product ───► out_of_scope   (stops here, $0)
    │
extraction  (reported events + events read from the narrative)
    ├──► meddra ──► seriousness     ICH E2A: LLM reads criteria, a rule decides
    ├──► causality                  temporal, conservative by default
    └──► expectedness               RAG over the package insert + confidence gate
                  │ (join)
                  ▼
precedent ──► influence (IME list, past cases) ──► human_review ⏸ ──► finalize (audit trail)
```

A LangGraph workflow (not an agent), with the three judgments running in parallel. The review gate is a LangGraph `interrupt`, checkpointed so a paused case survives a restart.

**Deployment:** browser → **Next.js** (UI + backend-for-frontend) → **FastAPI** → OpenAI. Two containers on **AWS App Runner** (Tokyo). The browser never calls the API: the Next.js server proxies to it with a shared secret, so there is no CORS and the API returns 403 to anyone else. The same images run locally with `docker compose up`.

## Design decisions

The depth lives in the [Architecture Decision Records](docs/adr/) (context, options, decision, consequences — each linked to the experiment behind it).

- **LLM interprets, rules decide.** For seriousness the model reads the narrative for each ICH E2A criterion (catching euphemisms and attribution); a deterministic rule turns criterion hits into a verdict. For expectedness the model classifies the match type, and a gate maps it to 既知 / 要確認 / 未知. Judgments stay auditable. [ADR 0002](docs/adr/0002-expectedness-confidence-gate.md), [0004](docs/adr/0004-seriousness-e2a-llm-plus-deterministic.md)
- **Hybrid retrieval for MedDRA.** Character-bigram BM25 plus vectors, fused with RRF, with a deterministic exact-match fast path — no Japanese tokenizer needed. [ADR 0003](docs/adr/0003-meddra-retrieval-hybrid.md)
- **A workflow, not an agent.** The steps and their order are fixed by the domain, so a fixed graph is more explainable and testable than a tool-choosing agent. [ADR 0006](docs/adr/0006-langgraph-orchestration.md)
- **Human in the loop that changes later cases.** Promoting a PT to the IME list makes future events on it serious automatically; approved cases become precedent, which can only move a verdict to the safe side. [ADR 0007](docs/adr/0007-hitl-approval-interrupt.md)–[0010](docs/adr/0010-past-data-influence-mode.md)
- **Cost / privacy ladder, measured.** Embeddings and generation are swappable per step. A per-step benchmark of five local models found none of the 7–8B models keeps under-calls at 0, so the local option is a hybrid: transcription and coding run locally, the clinical judgments stay on the frontier model. [ADR 0011](docs/adr/0011-local-embedding-provider.md), [0012](docs/adr/0012-local-generation-per-step.md)
- **Backend-for-frontend.** Replacing the original Streamlit UI with Next.js needed no backend change, because the API split existed from the start. [ADR 0013](docs/adr/0013-nextjs-frontend-bff.md)
- **Demo protections enforced on the server.** Sample-only input is enforced in the BFF (the case builder sends fields; the server renders the report), with per-IP and daily caps and a hard spending cap at the provider.
- **Cost measured, not estimated.** A LangChain callback on the graph run attributes tokens and time to each step, without the services knowing they are measured.
- **Bilingual, with the line drawn at the model.** The UI, fixed vocabularies and MedDRA terms are English under `/en/`; case text and the model's rationales stay Japanese, because the pipeline and its evaluation are Japanese. The review form shows "Needs review" but sends `要確認`, and a test proves it.
- **Understand it, then accelerate it.** The first RAG pipeline was written directly on the OpenAI and Chroma SDKs (tag `v0.1-scratch-rag`), then migrated to LangChain.

## Tech stack

Python 3.12 · FastAPI · LangChain / LangGraph · Chroma · Pydantic v2 · OpenAI (gpt-4o / 4o-mini, text-embedding-3-small), optional local models via Ollama · Next.js 16 (App Router, TypeScript, Tailwind v4) · Playwright · Docker · AWS App Runner, ECR, SSM

## Run it locally

Requires Docker and an OpenAI API key.

```bash
git clone https://github.com/nabeofchanKo/pv-rag-assistant.git
cd pv-rag-assistant
cp .env.example .env        # set OPENAI_API_KEY
docker compose up --build   # UI :3000, API docs :8000/docs
```

Locally, uploads are enabled (`DEMO_MODE=0`); the public demo keeps them off.

<details>
<summary>Without Docker</summary>

Requires Python 3.12+ and Node.js 20+.

```bash
python -m venv venv && source venv/bin/activate   # Windows (Git Bash): source venv/Scripts/activate
pip install -r backend/requirements.txt
venv/bin/uvicorn app.main:app --app-dir backend --reload   # terminal 1: API

cd web && npm install && npm run dev                        # terminal 2: UI
```

</details>

### Tests

```bash
venv/bin/python -m pytest backend/tests -q                        # 178 tests
cd web && npx playwright install chromium && npm run test:e2e     # 7 browser tests
```

- **Backend:** unit tests on fakes (no API calls); a **safety gate** that exhausts every input the deterministic decision layer can receive and proves no model output can turn into an under-call (the model interprets, code decides — so the invariant holds by construction, and the evaluation measures the rest); and a **contract test** keeping the Pydantic models and the TypeScript types in sync.
- **E2E:** a real browser and the real BFF against a fake backend that replays responses **recorded from the real one** — free and deterministic. It checks that what the BFF forwards on approval is exactly what the real backend accepted, in both languages. Re-record with `web/e2e/record_fixtures.py`.

## API

| Method | Endpoint | |
|---|---|---|
| `POST` | `/cases/triage` | Triage a case → a draft paused for review (or `out_of_scope`) |
| `GET` | `/cases/{thread_id}` | Reload a draft or a finalized result |
| `POST` | `/cases/{thread_id}/approve` | Approve or reject, with overrides → result + audit trail |
| `POST` | `/documents/upload` | Index a document for Q&A |
| `POST` | `/query` | Ask a question → answer + cited sources |

Full schemas at `/docs` (OpenAPI).

## Repository

```
backend/app/        FastAPI app: routers/, services/ (one per triage step, triage_graph.py, telemetry.py), schemas.py
backend/tests/      unit, contract and safety-invariant tests
web/src/            Next.js: app/[lang]/ (pages), app/api/ (BFF), components/triage/, i18n/
web/e2e/            Playwright suite, fake backend, fixture recorder
data/               synthetic cases, gold set, package inserts, MedDRA sample, product master, IME list
experiments/        evaluation write-ups + the scripts that reproduce them
docs/adr/           architecture decision records
```

## Limitations

- **Small evaluation** (see [Evaluation](#evaluation)); run-to-run variation is measured on 3 runs, not with confidence intervals.
- **Japanese only on the input side.** The pipeline, reference data and gold set are Japanese; the English UI translates the interface, not the model's output.
- **Demo state is ephemeral.** Review threads, precedent and IME promotions live in the container and reset on deploy. The upgrade path (a Postgres checkpointer) is documented in ADR 0013, not built.
- **E2E tests replay recorded responses**, so they catch UI/BFF regressions, not changes in the backend's answers (that is the evaluation harness's job).

## Data

All cases are **synthetic**, written for this project; no real patient data. The package inserts are fictional, and the MedDRA file is a small illustrative subset (MedDRA is licensed).
