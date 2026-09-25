# PV RAG Assistant

**A retrieval-augmented assistant for pharmacovigilance (PV) — grounding every answer in the source safety report.**
**医薬品安全性監視（PV）業務のための、根拠提示型 RAG アシスタント。すべての回答を出典に紐づけます。**

🌐 **[English](#english)** ｜ **[日本語](#日本語)**

> **Status / 状況:** Active development. The triage assistant is **deployed and publicly runnable** — see the live demo below. Phases 0–6 complete; see the [Roadmap](#roadmap).

### 🚀 Live demo / デモ

**https://h4b6m4zyqj.ap-northeast-1.awsapprunner.com**

Runs the real pipeline against bundled synthetic cases. Pick a sample, or build your own case
with the case builder and watch the assessment respond to what you wrote in the narrative.
No sign-up. / 同梱の合成症例で実際のパイプラインが動きます。症例ビルダーで自分で症例を組み立てることもできます。

> The public demo accepts **only the bundled sample cases and builder-composed cases** (no file upload),
> and is rate limited — it calls a paid LLM API.
> / 公開デモは費用管理のため、同梱サンプルとビルダーで作成した症例のみを受け付け、実行回数を制限しています。

---

<a name="english"></a>
## English

A Retrieval-Augmented Generation (RAG) application specialized for **pharmacovigilance (PV)** — the practice of monitoring and assessing adverse drug reactions. It ingests Individual Case Safety Reports (ICSRs) and answers natural-language questions about reported adverse events, grounding every answer in the source documents with a citation.

This project is both a **portfolio piece** and a **learning vehicle**: the goal is not only a working app, but a system whose every design choice I can explain. It was first built from scratch on vendor SDKs to understand each RAG step, then migrated to LangChain for velocity (see [Design decisions](#design-decisions)).

### Why pharmacovigilance?

In drug-safety operations, the cost of a hallucinated or unsourced answer is high — incorrect adverse-event information has real clinical and regulatory consequences. This project treats **source traceability** and **hallucination resistance** as first-class design constraints, not afterthoughts. The domain was chosen to align with prior professional experience in pharmacovigilance (adverse-event evaluation and bilingual JP/EN regulatory documentation).

### What it does

- **Triage a case** — the main flow. Feed it a case report (PDF, text, email or a scanned
  image) and it produces a first-pass assessment: own-company product gate → extraction of
  patient and adverse events (**including events that appear only in the narrative**) →
  MedDRA PT coding → seriousness against ICH E2A, expectedness against the package insert,
  and temporal causality → consistency against past approved cases.
- **Review and approve (human in the loop)** — the draft pauses for a reviewer, who can
  override any verdict, correct the extraction, and promote a PT to the medically-important
  events list. Every change keeps the original value as an audit trail, and an approval
  becomes precedent for later cases.
- **Ask (RAG Q&A)** — the original flow: index a report and ask questions about it.
- **Trace** — every judgment carries its evidence: the quoted case text, the E2A criterion
  it met, or the passage of the insert it matched. Nothing is asserted without a source.

The safety posture is deliberate throughout: uncertain judgments land on the conservative
side (要確認 / 否定できない) and are surfaced for a human rather than silently resolved, because
in drug safety an under-call is far more costly than an over-call.

### Architecture

```
PDF upload (Japanese ICSR)
    │
    ▼
PDFProcessor        ── extracts text per page (pdfplumber), normalizes (NFKC) — kept custom for JP
    │
    ▼
FixedLengthChunker  ── token-based chunking via LangChain TokenTextSplitter (500 / 100 overlap)
    │                  behind a ChunkingStrategy interface
    ▼
Chroma vector store ── LangChain langchain-chroma; embeds (OpenAIEmbeddings) + stores + searches (cosine)
    │
    ▼
GeneratorService    ── LCEL chain: prompt | ChatOpenAI(temperature=0) | StrOutputParser
    │
    ▼
answer + source citations
```

The pipeline is exposed via a **FastAPI** backend and consumed by a **Next.js** frontend, which reaches it through its own server (a backend-for-frontend) rather than from the browser — so there is no CORS and the API never has to be public. Because that split existed from the start, replacing the original Streamlit UI in Phase 6 required **no backend change at all** (see [ADR 0013](docs/adr/0013-nextjs-frontend-bff.md)). Both the embedding model and the chat model are injected as swappable LangChain abstractions, so they can be exchanged (e.g. for local models) without touching the pipeline.

### Tech stack

| Layer               | Choice                                             |
| ------------------- | -------------------------------------------------- |
| RAG orchestration   | LangChain 1.x (LCEL)                               |
| Backend API         | FastAPI                                            |
| Frontend            | Next.js 16 (App Router, TypeScript, Tailwind v4) via a BFF |
| Packaging           | Docker (multi-stage, non-root); `docker compose up` runs the whole stack |
| Deployment          | AWS App Runner ×2 (web + API) from ECR, ap-northeast-1 |
| PDF parsing         | pdfplumber (custom processor, NFKC normalization)  |
| Text splitting      | LangChain `TokenTextSplitter` (tiktoken cl100k_base)|
| Embeddings          | OpenAI `text-embedding-3-small` (default) — or local `bge-m3` via Ollama (opt-in, on-prem); swappable behind DI |
| Vector store        | Chroma (via langchain-chroma, cosine)              |
| Generation          | OpenAI per-step (4o / 4o-mini, temp 0) by default — or a local model via Ollama (opt-in; benchmarked per step, see ADR 0012); swappable behind DI |
| Data validation     | Pydantic v2                                        |
| Config              | pydantic-settings                                  |

<a name="design-decisions"></a>
### Design decisions

A few deliberate choices that shaped the implementation:

- **Built from scratch first, then migrated to LangChain.** The pipeline was initially implemented directly on the OpenAI and ChromaDB SDKs to make every RAG step explicit and understood. That from-scratch version is preserved at git tag `v0.1-scratch-rag`. It was then migrated to LangChain (adopting LangChain components inside the existing service architecture) for development velocity — so the repository tells a "understand it, then accelerate it" story.
- **Swappable models behind interfaces.** The embedding model and the chat model are provided via dependency injection as LangChain `Embeddings` / `BaseChatModel` abstractions. This sets up a planned **cost / privacy ladder**: start on the OpenAI API, then evaluate local models (e.g. a Japanese embedding model, or a local medical LLM) so sensitive safety data can stay on-premise.
- **Strategy pattern for chunking.** Chunking sits behind an abstract `ChunkingStrategy` interface, so alternative strategies can be added and compared without touching calling code.
- **Custom PDF processing kept on purpose.** Rather than a stock LangChain loader, PDF text extraction stays custom to apply **NFKC normalization**, which matters for consistent Japanese text.
- **Immutable domain models.** Domain objects (`Chunk`, `ProcessedDocument`, …) are frozen Pydantic models, safe to pass around and reason about.
- **Hallucination guardrails.** Generation uses `temperature=0` and a system prompt that constrains answers to the provided context and declines when information is absent. The internal `Chunk` model maps to a separate public `SourceInfo` model so responses expose only what is needed.
- **Source traceability.** Page numbers are preserved from extraction through to the final response, so every answer can cite its document and page.
- **Decisions and experiments are recorded.** Significant design choices live as [Architecture Decision Records](docs/adr/) (Context / Options / Decision / Consequences), each linking to the reproducible [experiment](experiments/) that produced its evidence — e.g. the expectedness confidence gate and the MedDRA hybrid-retrieval choice.

### Project structure

```
pv-rag-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── config.py          # settings (pydantic-settings); model providers are configurable
│   │   ├── dependencies.py    # DI: swappable embeddings / chat model + services
│   │   ├── exceptions.py      # custom PDF-processing exceptions
│   │   ├── schemas.py         # Pydantic domain & API models
│   │   ├── routers/
│   │   │   ├── documents.py   # POST /documents/upload
│   │   │   └── query.py       # POST /query
│   │   └── services/
│   │       ├── pdf_processor.py  # PDF text extraction (pdfplumber + NFKC)
│   │       ├── chunking.py       # ChunkingStrategy + LangChain-backed FixedLengthChunker
│   │       ├── retriever.py      # LangChain Chroma vector store (embed + store + search)
│   │       └── generator.py      # LCEL context-grounded generation
│   ├── requirements.txt
│   └── requirements-dev.txt
│   └── Dockerfile             # multi-stage, non-root, tiktoken cache baked in
├── web/                       # Next.js frontend + BFF
│   ├── src/app/
│   │   ├── api/               # BFF route handlers -> FastAPI (no CORS, key stays server-side)
│   │   ├── triage/            # triage screen: samples, case builder, HITL review
│   │   ├── rag/               # RAG Q&A screen
│   │   └── samples/           # what each bundled case is designed to probe
│   ├── src/components/triage/ # result view, review panel, case builder
│   ├── src/lib/               # typed API contract, demo policy, rate limits
│   └── Dockerfile
├── compose.yaml               # whole stack in one command
├── data/
│   ├── sample_reports/        # synthetic Japanese ICSRs (.txt source + .pdf)
│   └── meddra_sample/         # sample MedDRA subset (for upcoming MedDRA features)
├── .env.example
└── README.md
```

### Getting started

**Prerequisites:** Docker, and an OpenAI API key.

```bash
git clone https://github.com/nabeofchanKo/pv-rag-assistant.git
cd pv-rag-assistant

cp .env.example .env
# then edit .env and set OPENAI_API_KEY
```

The whole stack in one command:

```bash
docker compose up --build
```

UI at http://localhost:3000, API docs at http://localhost:8000/docs. Compose runs
the local stack with `DEMO_MODE=0`, so you can upload your own case files; the
deployed demo leaves it on.

<details>
<summary>Running it without Docker</summary>

**Prerequisites:** Python 3.12+ and Node.js 20+.

```bash
python -m venv venv
source venv/bin/activate         # macOS/Linux
# source venv/Scripts/activate   # Windows (Git Bash)
pip install -r backend/requirements.txt

# Terminal 1 — API (from project root)
venv/bin/uvicorn app.main:app --app-dir backend --reload

# Terminal 2 — web
cd web && npm install && npm run dev
```

</details>

### API

| Method | Endpoint            | Description                                          |
| ------ | ------------------- | ---------------------------------------------------- |
| `POST` | `/documents/upload` | Upload and index a PDF                               |
| `POST` | `/query`            | Ask a question; returns an answer with cited sources |
| `POST` | `/cases/triage`     | Triage a case: product match + extraction + MedDRA PT + seriousness (ICH E2A) + causality (temporal) + expectedness (既知/未知) |
| `GET`  | `/`                 | Health check                                         |

Interactive API documentation is auto-generated at `/docs`.

<a name="roadmap"></a>
### Roadmap

The end goal is not "ask questions about a report" but a **triage / first-pass safety-evaluation assistant**: given an adverse-event report, produce an evidence-backed *draft* assessment (drugs involved, adverse events — including those inferable only from the narrative — MedDRA suggestions, expectedness, seriousness, and causality), with a human-in-the-loop approval step.

- [x] **Phase 0 — Foundation:** end-to-end RAG (extract → chunk → embed → store → retrieve → generate), migrated to LangChain; Japanese sample data; bilingual README.
- [ ] **Phase 1 — Input expansion:** ingest PDFs, scanned handwritten memos (image OCR), and email-format text reports behind one ingestion layer.
- [ ] **Phase 2 — Structured extraction:** extract drugs / adverse events / patient info; match drugs against a company product master; read adverse events that appear only in the narrative.
- [ ] **Phase 3 — Evaluation tasks:** MedDRA term suggestion, expectedness (vs. package insert), seriousness (ICH E2A criteria), and causality (temporal reasoning), each grounded with citations.
- [ ] **Phase 4 — Orchestration:** connect the steps as an explainable workflow (LangGraph) with a human-in-the-loop propose → approve step.
- [ ] **Phase 5 — Evaluation & cost/privacy:** retrieval metrics (Hit Rate@k / MRR) and answer quality (faithfulness); evaluate local embedding / generation models on cost × privacy × performance.
- [x] **Phase 6 — Frontend & deployment:** Next.js frontend behind a BFF (replacing Streamlit, no backend change), the whole stack containerized, deployed to AWS App Runner with demo protections. See the [design note](#design-note--phase-6-frontend--deployment) and [ADR 0013](docs/adr/0013-nextjs-frontend-bff.md).

### Design note — expectedness (既知/未知)

Expectedness (is an adverse event already described in the drug's package insert?) is implemented as **Approach A: RAG retrieval over the insert text.** The package insert is chunked and embedded; for each adverse event we retrieve the most relevant "副作用" (adverse-reaction) passages of that drug's insert and an LLM judges *listed (既知)* / *not listed (未知)* / *undetermined*, returning the cited passage as evidence. This reuses the existing retrieval stack and keeps the judgment grounded, with **未知 as the safe default** when no supporting passage is found.

**Future extension — Approach C (hybrid, to A/B test):** read each insert *once* with an LLM to extract its adverse-reaction section into a structured, source-cited ADR list, cache it, then match each adverse event against that list. This trades per-query retrieval for a deterministic, auditable list (closer in spirit to the deterministic product-master matching). Worth benchmarking against Approach A on accuracy × cost once Approach A is in place.

### Design note — local embedding tier (Phase 5a)

The **cost / privacy ladder** now has its first local rung. `get_embeddings()` dispatches on `EMBEDDING_PROVIDER` — `openai` (default) or `ollama`, a local model (e.g. `bge-m3`) served by Ollama so case text never leaves the machine. Because a vector store is bound to one embedding dimension, the Chroma store is namespaced per embedding model, so both providers coexist and switching is a flag flip (the reference collections re-index at startup). A deterministic, LLM-free [retrieval bench](experiments/embedding_retrieval_bench.md) shows local `bge-m3` matches OpenAI `text-embedding-3-small` on the retrieval the system actually uses (hybrid hit@3 = 100% on both; the only gap is one term at vector-only rank-1, absorbed by the BM25/exact fusion), and an end-to-end run keeps the under-call-0 safety invariant. Local's win is privacy + zero marginal cost + no quota, **not** latency (LangChain's Ollama embedder is sequential, so per-query it is slower here). OpenAI stays the default; local is a validated opt-in. See [ADR 0011](docs/adr/0011-local-embedding-provider.md).

### Design note — local generation, per step (Phase 5b)

Generation is swappable the same way (`CHAT_PROVIDER=ollama`, one `OLLAMA_CHAT_MODEL` for every step). Because a full end-to-end triage on a local 7B is impractical (~10-15 min/case), a [per-step comparison harness](experiments/scripts/generation_bench.py) benchmarks each step in isolation over the gold set — which is also exactly the "where does local hold vs break" question — reporting **under-calls first**. Across OpenAI vs qwen2.5:7b / ELYZA-JP-8B / gemma3:4b / medllama2, the [result](experiments/generation_comparison.md) is clear: **no local 7-8B preserves the under-call-0 safety invariant** — every one misses a serious event on the hard-narrative seriousness step. **ELYZA-JP-8B is the strongest local** (extraction 91%, beating OpenAI's 87%; MedDRA and causality 100%) and is viable for extraction / coding / the conservative causality default, but the safety-critical judgments still need the frontier model. The honest cost×privacy answer is therefore **hybrid per-step**, and it is wired: `CHAT_PROVIDER=hybrid` runs the transcription/coding steps (extraction, narrative, MedDRA) on the local model — ELYZA-JP-8B, the bench winner — and keeps the three clinical judgments on OpenAI, so the under-call-0 safety invariant is preserved by construction (the judgment code + models are unchanged) while the high-volume steps go on-prem. The Ollama path is hardened (`num_ctx`/`num_predict`/timeout) so a local model can't run away or hang the pipeline. See [ADR 0012](docs/adr/0012-local-generation-per-step.md).

### Design note — Phase 6 frontend & deployment

The Streamlit UI was replaced by a Next.js app **without changing a single line of
the backend**. That was possible because the split already existed: every phase
had been built behind the FastAPI REST API, and Streamlit was itself just an HTTP
client. Phase 6 was therefore a frontend swap, not new development.

**Backend-for-frontend.** The browser talks only to the Next.js server, whose route
handlers proxy to FastAPI server-to-server. That buys three things at the cost of
one extra hop: no CORS, no API key in the browser bundle, and an API that does not
have to be publicly reachable. The typed contract in `web/src/lib/types.ts` mirrors
`backend/app/schemas.py` by hand — small and stable enough not to warrant codegen,
with a contract test as the planned mitigation for drift.

**Everything is a container.** `docker compose up` runs the whole stack, and the
*same images* run in production on two App Runner services. Choosing containers for
both ends over a managed frontend host was deliberate: it keeps one build system and
makes "the stack is containerized" true in production, at the cost of a CDN.

**Reading the result.** The triage view is scanned under time pressure, so it leads
with a summary (counts, and the serious-and-not-in-the-label events that drive
expedited reporting), then gives **one row per adverse event** carrying all four
verdicts, with the evidence behind a per-row disclosure. An earlier version repeated
the same event list across four tables, which made the page long and gave "what was
decided" and "why" the same visual weight.

**Showing what the human and the history contributed.** Where a verdict differs from
what the model first produced — because the reviewer overrode it, or because the IME
list or past-case precedent adjusted it — the original is shown struck through beside
the adjusted value, and every adjustment is listed with its source. The "before"
verdict is reconstructed from a **single run** (`InfluenceItem.from_verdict`);
re-running the case to obtain a baseline would fold in LLM run-to-run variation and
stop isolating the effect, which is the same reasoning the evaluation harness uses.

**Case builder.** Fixed samples show that the pipeline works but not what it does
under a case you care about, so the UI can compose one from constrained fields. The
client sends fields, never a document — the BFF validates them and renders the report
text itself, which is what lets this coexist with the demo restrictions below.

**Demo protections.** The public demo calls a paid API, so: input is restricted to the
bundled samples and builder-composed cases (**enforced server-side**, not by hiding the
file picker), requests are rate limited per IP and capped globally per day, and the API
requires a shared secret from the BFF so it cannot be called directly. A hard spending
cap at the LLM provider sits behind all of it as the only real guarantee.

### Known limitations (current MVP)

- Dense-vector retrieval can be confused by documents that share a common format/vocabulary, and is weaker on proper nouns (e.g. distinguishing one drug or reporter name from another). Hybrid retrieval is on the roadmap.
- Token-based chunking can split mid-character on Japanese text, so per-chunk character offsets are best-effort (they are metadata only and do not affect retrieval or answers). A Japanese-aware splitter is a Phase 5 improvement.
- The frontend has no automated tests yet (the backend has 74, mostly API-free fakes). A contract test between the hand-written TypeScript types and the OpenAPI schema, plus an end-to-end smoke test, are the next additions.
- Error handling is fail-fast (MVP); production hardening (retries, rate-limit handling, structured errors) is planned.

### Note on data

The sample reports in `data/sample_reports/` are **synthetic** ICSRs created for this project; they contain no real patient data. The MedDRA sample is a small illustrative subset, as the full MedDRA terminology is licensed.

---

<a name="日本語"></a>
## 日本語

**医薬品安全性監視（ファーマコビジランス, PV）** に特化した RAG（検索拡張生成）アプリケーションです。個別症例安全性報告（ICSR）を取り込み、報告された有害事象に関する自然言語の質問に回答します。**すべての回答を出典（文書名・ページ番号）に紐づける**ことを重視しています。

本プロジェクトは **ポートフォリオ** であると同時に **学習の場** です。目的は「動くアプリ」だけでなく、**すべての設計判断を自分の言葉で説明できる状態**にすること。そのため、まず各RAGステップを理解するためにフレームワークを使わず自作し、その後に開発速度のためLangChainへ移行しました（[設計判断](#設計判断)参照）。

### なぜ安全性監視（PV）か

安全性業務では、幻覚（ハルシネーション）や出典不明の回答のコストが非常に高く、誤った有害事象情報は臨床・規制上の実害につながります。本プロジェクトは **出典トレーサビリティ** と **ハルシネーション耐性** を後付けではなく第一級の設計制約として扱います。この領域は、有害事象評価および日英バイリンガルの規制文書作成という実務経験に基づいて選びました。

### 何ができるか

- **症例のトリアージ** — 本体の機能。症例報告（PDF／テキスト／メール／スキャン画像）を投入すると、
  一次評価案を生成します：自社品判定（ゲート）→ 患者・有害事象の抽出（**経過からしか読み取れない事象を含む**）
  → MedDRA PT コード提案 → 重篤度（ICH E2A）・既知/未知（添付文書との照合）・因果関係（時間的）→ 過去承認症例との整合。
- **レビューと承認（HITL）** — ドラフトは人手レビューで一時停止します。判定の上書き、抽出の修正、
  医学的に重要な事象（IME）リストへのPT昇格が可能で、**変更は必ず元の値を残して監査証跡化**されます。
  承認された症例は以後の判例になります。
- **質問（RAG Q&A）** — 当初からの機能。報告書を索引化して内容を質問できます。
- **追跡** — すべての判定が根拠を伴います（症例本文の引用、該当したE2A基準、添付文書の該当箇所）。
  出典なしに何かを断定することはありません。

安全側への寄せ方は一貫した設計方針です。確信が持てない判定は保守的な側（要確認／否定できない）に置き、
黙って解決せず人手に上げます。安全性業務では**過小評価のコストが過大評価より圧倒的に高い**ためです。

### アーキテクチャ

```
PDF アップロード（日本語 ICSR）
    │
    ▼
PDFProcessor        ── ページ単位でテキスト抽出（pdfplumber）＋NFKC正規化（日本語のため自作を維持）
    │
    ▼
FixedLengthChunker  ── LangChain TokenTextSplitter によるトークン分割（500 / 重複100）
    │                  ChunkingStrategy インターフェース経由
    ▼
Chroma ベクトルストア ── LangChain langchain-chroma。埋め込み（OpenAIEmbeddings）＋保存＋検索（cosine）
    │
    ▼
GeneratorService    ── LCEL チェーン: prompt | ChatOpenAI(temperature=0) | StrOutputParser
    │
    ▼
回答 ＋ 出典
```

パイプラインは **FastAPI** バックエンドとして公開し、**Next.js** フロントエンドが利用します。ブラウザから直接ではなく Next.js のサーバー側（BFF）経由で呼ぶため、**CORS が不要**で、APIを公開せずに済みます。この分離が最初からあったため、Phase 6 で Streamlit を置き換える際に**バックエンドの変更は一切不要**でした（[ADR 0013](docs/adr/0013-nextjs-frontend-bff.md)）。埋め込みモデルとチャットモデルは、差し替え可能な LangChain の抽象として注入されるため、パイプラインを触らずに（例：ローカルモデルへ）交換できます。

### 技術スタック

| レイヤー             | 採用                                                 |
| -------------------- | ---------------------------------------------------- |
| RAG オーケストレーション | LangChain 1.x（LCEL）                             |
| バックエンドAPI      | FastAPI                                              |
| フロントエンド       | Next.js 16（App Router / TypeScript / Tailwind v4）＋ BFF |
| パッケージング       | Docker（マルチステージ・非root）。`docker compose up` で全体が起動 |
| デプロイ             | AWS App Runner ×2（web / API）、ECR、東京リージョン |
| PDF解析              | pdfplumber（自作プロセッサ、NFKC正規化）            |
| テキスト分割         | LangChain `TokenTextSplitter`（tiktoken cl100k_base）|
| 埋め込み             | OpenAI `text-embedding-3-small`（既定）／ ローカル `bge-m3`（Ollama・オンプレ・オプトイン）。DI背後で差し替え可 |
| ベクトルストア       | Chroma（langchain-chroma経由・cosine）              |
| 生成                 | 既定はOpenAIのステップ別（4o / 4o-mini・temp 0）／ ローカルモデル（Ollama・オプトイン・ステップ別ベンチ済み、ADR 0012）。DI背後で差し替え可 |
| データ検証           | Pydantic v2                                          |
| 設定                 | pydantic-settings                                    |

<a name="設計判断"></a>
### 設計判断

実装を形づくった、意図的な選択をいくつか挙げます。

- **まず自作、その後LangChainへ移行。** 最初は OpenAI・ChromaDB の SDK を直接使い、各RAGステップを明示的に理解しながら実装しました。その自作版は git タグ `v0.1-scratch-rag` として保存しています。その上で、開発速度のため（既存のサービス構成を保ったまま内部部品をLangChain化する形で）LangChainへ移行しました。リポジトリ自体が「理解してから加速する」物語になっています。
- **モデルはインターフェース越しに差し替え可能。** 埋め込みモデルとチャットモデルは、LangChain の `Embeddings` / `BaseChatModel` 抽象として DI で注入します。これは計画中の **コスト／プライバシーのはしご** の土台です：まず OpenAI API から始め、その後ローカルモデル（日本語埋め込みモデルやローカル医療LLM等）を評価し、機微な安全性データを外部に出さない構成へ拡張できます。
- **チャンク化はStrategyパターン。** `ChunkingStrategy` 抽象の背後に実装があるため、呼び出し側を変えずに別戦略を追加・比較できます。
- **PDF処理はあえて自作を維持。** 既製のLangChainローダーではなく、**NFKC正規化**を適用するため自作を維持しています（日本語テキストの一貫性に効きます）。
- **不変ドメインモデル。** `Chunk` / `ProcessedDocument` 等は frozen な Pydantic モデルで、安全に受け渡し・推論できます。
- **ハルシネーション対策。** 生成は `temperature=0`、かつ「提供された文脈のみに基づき、情報が無ければ回答を控える」システムプロンプトで制約します。内部の `Chunk` モデルは公開用の `SourceInfo` モデルに変換し、APIは必要な情報のみ公開します。
- **出典トレーサビリティ。** ページ番号を抽出から最終回答まで一貫して保持し、すべての回答が文書とページを引用できます。
- **意思決定と実験を記録。** 重要な設計判断は [ADR（Architecture Decision Records）](docs/adr/) として残し（背景／選択肢／決定／結果）、各ADRは根拠となる再現可能な[実験記録](experiments/)にリンクします（例：既知/未知の確信度ゲート、MedDRA のハイブリッド検索採用）。

### プロジェクト構成

```
pv-rag-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI エントリポイント
│   │   ├── config.py          # 設定（pydantic-settings）。モデルプロバイダは設定可能
│   │   ├── dependencies.py    # DI：差し替え可能な埋め込み／チャットモデル＋各サービス
│   │   ├── exceptions.py      # PDF処理の独自例外
│   │   ├── schemas.py         # Pydantic ドメイン／APIモデル
│   │   ├── routers/
│   │   │   ├── documents.py   # POST /documents/upload
│   │   │   └── query.py       # POST /query
│   │   └── services/
│   │       ├── pdf_processor.py  # PDFテキスト抽出（pdfplumber + NFKC）
│   │       ├── chunking.py       # ChunkingStrategy ＋ LangChainベースの FixedLengthChunker
│   │       ├── retriever.py      # LangChain Chroma ベクトルストア（埋め込み＋保存＋検索）
│   │       └── generator.py      # LCEL による文脈準拠の生成
│   ├── requirements.txt
│   └── requirements-dev.txt
│   └── Dockerfile             # マルチステージ・非root・tiktokenキャッシュ同梱
├── web/                       # Next.js フロントエンド＋BFF
│   ├── src/app/
│   │   ├── api/               # BFFルート → FastAPI（CORS不要・鍵はサーバー側）
│   │   ├── triage/            # トリアージ画面：サンプル・症例ビルダー・HITLレビュー
│   │   ├── rag/               # RAG Q&A 画面
│   │   └── samples/           # 各サンプル症例の「狙い」
│   ├── src/components/triage/ # 結果表示・レビューパネル・症例ビルダー
│   ├── src/lib/               # 型付きAPI契約・デモ保護・レート制限
│   └── Dockerfile
├── compose.yaml               # 1コマンドでスタック全体
├── data/
│   ├── sample_reports/        # 合成の日本語ICSR（.txt原本＋.pdf）
│   └── meddra_sample/         # MedDRAサンプル部分集合（今後のMedDRA機能用）
├── .env.example
└── README.md
```

### セットアップ

**前提:** Docker、OpenAI APIキー。

```bash
git clone https://github.com/nabeofchanKo/pv-rag-assistant.git
cd pv-rag-assistant

cp .env.example .env
# .env を編集し OPENAI_API_KEY を設定
```

1コマンドでスタック全体が起動します。

```bash
docker compose up --build
```

UI: http://localhost:3000 ／ APIドキュメント: http://localhost:8000/docs

compose はローカルを `DEMO_MODE=0` で起動するため、自分の症例ファイルをアップロードして試せます
（公開デモ側はデモ保護を有効のままにしています）。

<details>
<summary>Docker を使わずに起動する場合</summary>

**前提:** Python 3.12以上、Node.js 20以上。

```bash
python -m venv venv
source venv/bin/activate         # macOS/Linux
# source venv/Scripts/activate   # Windows (Git Bash)
pip install -r backend/requirements.txt

# ターミナル1 — API（プロジェクトルートから）
venv/bin/uvicorn app.main:app --app-dir backend --reload

# ターミナル2 — web
cd web && npm install && npm run dev
```

</details>

### API

| メソッド | エンドポイント       | 説明                                        |
| -------- | -------------------- | ------------------------------------------- |
| `POST`   | `/documents/upload`  | PDFをアップロードしてインデックス化          |
| `POST`   | `/query`             | 質問を送信。出典付きの回答を返す             |
| `POST`   | `/cases/triage`      | 症例をトリアージ：自社品判定＋抽出＋MedDRAコード提案＋重篤度判定（E2A）＋因果関係（時間的）＋既知/未知判定 |
| `GET`    | `/`                  | ヘルスチェック                              |

対話的なAPIドキュメントは `/docs` に自動生成されます。

### ロードマップ

最終目標は「報告書に質問する」ことではなく、**トリアージ／一次評価案の作成支援** です。有害事象報告を入力として、根拠付きの評価 *案*（関与薬剤、有害事象＝経過からしか読み取れないものを含む、MedDRA提案、既知／未知、重篤度、因果関係）を生成し、人間による承認（HITL）を挟みます。

- [x] **Phase 0 — 基盤:** エンドツーエンドのRAG（抽出→チャンク→埋め込み→保存→検索→生成）をLangChainへ移行、日本語サンプルデータ、日英READMEを整備。
- [ ] **Phase 1 — 入力の多様化:** PDF・手書きメモのスキャン（画像OCR）・メール形式のテキスト報告を、単一の取り込み層の背後で扱う。
- [ ] **Phase 2 — 構造化抽出:** 薬剤／有害事象／患者情報を抽出、薬剤を自社製品マスタと照合、**経過にのみ現れる有害事象**を読み取る。
- [ ] **Phase 3 — 評価タスク:** MedDRAコード提案、既知／未知判定（添付文書との照合）、重篤度判定（ICH E2A基準）、因果関係判定（時間的関係）を、それぞれ出典付きで。
- [ ] **Phase 4 — オーケストレーション:** 各ステップを説明可能なワークフロー（LangGraph）として連結し、提案→承認のHITLを挟む。
- [ ] **Phase 5 — 評価・コスト／プライバシー:** 検索評価（Hit Rate@k / MRR）と回答品質（faithfulness）を測定。ローカルの埋め込み／生成モデルを、コスト×プライバシー×性能で評価。
- [x] **Phase 6 — フロントエンド・デプロイ:** BFF 経由の Next.js フロントエンド（Streamlit を置き換え、バックエンド変更なし）、スタック全体のコンテナ化、AWS App Runner へデプロイ（デモ保護付き）。[設計メモ](#設計メモ--phase-6-フロントエンドデプロイ) と [ADR 0013](docs/adr/0013-nextjs-frontend-bff.md) 参照。

### 設計メモ — 既知／未知判定（expectedness）

既知／未知（その有害事象が添付文書に記載済みか）は **Approach A：添付文書テキストへの RAG 検索** で実装します。添付文書をチャンク化・埋め込みし、有害事象ごとに当該薬剤の「副作用」欄の関連箇所を検索して、LLM が *記載あり（既知）／記載なし（未知）／判定不能* を判定し、根拠となる引用文を返します。既存の検索基盤を再利用し、根拠に紐づけた判定を行います。裏付けとなる記載が見つからない場合は **未知を安全側の既定値** とします。

**今後の拡張 — Approach C（ハイブリッド、A/B比較の候補）:** 添付文書を **一度だけ** LLM で読み、副作用欄を出典付きの構造化 ADR リストへ抽出してキャッシュし、以後は各有害事象をそのリストと照合する方式。クエリごとの検索を、決定的で監査可能なリストに置き換える（決定的な自社品マスタ照合に思想が近い）。Approach A の実装後、精度×コストでベンチマークする価値がある。

### 設計メモ — ローカル埋め込みティア（Phase 5a）

**コスト／プライバシーの梯子** に最初のローカル段を追加しました。`get_embeddings()` は `EMBEDDING_PROVIDER` で分岐し、`openai`（既定）または `ollama`（Ollama が配信するローカルモデル、例 `bge-m3`）を選べます。後者では症例テキストが端末外に出ません。ベクトルストアは埋め込み次元に紐づくため、Chroma ストアを埋め込みモデル単位で名前空間分離し、両プロバイダを共存させてフラグ一つで切替可能にしています（参照コレクションは起動時に再インデックス）。決定的・LLM非依存の [検索ベンチ](experiments/embedding_retrieval_bench.md) では、ローカル `bge-m3` が実運用で使う検索（hybrid hit@3＝両者100%。差は vector単独のrank-1で1件のみで、BM25/exact融合が吸収）で OpenAI `text-embedding-3-small` と同等、end-to-end でも過小コール0の安全インバリアントを維持しました。ローカルの利点はプライバシー＋限界コスト0＋クォータ無しで、**レイテンシではありません**（LangChain の Ollama 埋め込みは逐次実行のため単発クエリはむしろ遅い）。既定は OpenAI のまま、ローカルは検証済みのオプトイン。[ADR 0011](docs/adr/0011-local-embedding-provider.md) 参照。

### 設計メモ — ローカル生成、ステップ別（Phase 5b）

生成も同様に差し替え可能です（`CHAT_PROVIDER=ollama`、全ステップを1つの `OLLAMA_CHAT_MODEL` で実行）。ローカル7BでのフルE2Eは約10-15分/症例と非現実的なため、[ステップ別比較ハーネス](experiments/scripts/generation_bench.py)で各ステップを分離計測し（＝「どこでローカルが持つ/崩れるか」の問いに直結）、**過小コールを最優先**で報告します。OpenAI vs qwen2.5:7b / ELYZA-JP-8B / gemma3:4b / medllama2 の[結果](experiments/generation_comparison.md)は明快で、**7-8Bのローカル勢はどれも過小コール0の安全インバリアントを保てません** — 全モデルが hard-narrative の重篤度で重篤事象を見落とします。**ELYZA-JP-8B が最良のローカル**（抽出91%でOpenAIの87%を上回り、MedDRA・因果は100%）で、抽出／コード化／保守的な因果既定には実用ですが、安全critな判定はやはり frontier モデルが必要です。よって正直なコスト×プライバシーの答えは **ステップ別ハイブリッド** で、実装済みです: `CHAT_PROVIDER=hybrid` は転記／コード化ステップ（抽出・narrative・MedDRA）をローカル（ベンチ勝者 ELYZA-JP-8B）で、3つの臨床判定は OpenAI で実行します。判定のコード・モデルは不変なので**過小コール0が構造上保たれ**つつ、高頻度ステップはオンプレに載ります。Ollama経路は暴走・ハングを防ぐよう `num_ctx`/`num_predict`/タイムアウトで堅牢化。[ADR 0012](docs/adr/0012-local-generation-per-step.md) 参照。

### 設計メモ — Phase 6 フロントエンド・デプロイ

Streamlit の UI を Next.js に置き換えましたが、**バックエンドは1行も変更していません**。
各フェーズを一貫して FastAPI の REST API の背後に作ってきたこと、そして Streamlit 自体が
HTTP クライアントに過ぎなかったことが理由です。Phase 6 は新規開発ではなく、フロント層の載せ替えでした。

**BFF（Backend for Frontend）。** ブラウザは Next.js のサーバーとだけ通信し、そのルートハンドラが
サーバー間通信で FastAPI を呼びます。ホップが1つ増える代わりに、**CORS 不要**・**APIキーがブラウザに出ない**・
**API を公開しなくてよい**、の3つが手に入ります。`web/src/lib/types.ts` の型は
`backend/app/schemas.py` を手書きでミラーしています（この規模ではコード生成の価値が薄いため）。
ズレのリスクは自覚しており、契約テストで検出する方針です。

**すべてコンテナ。** `docker compose up` でスタック全体が起動し、**同じイメージ**が本番の
App Runner 2サービスで動きます。フロントをマネージドホスティングに載せる選択肢もありましたが、
ビルド系統を1つに保ち「コンテナで完結している」を本番でも事実にするため、あえてコンテナに統一しました
（CDN を諦めるトレードオフ）。

**結果の読ませ方。** トリアージ画面は時間に追われながら走査されるので、まず**サマリー**
（件数と、迅速報告の検討対象になる「重篤かつ既知でない」事象）を出し、続いて**1事象＝1行**で
4つの判定を並べ、根拠は行の展開に収めています。以前は同じ事象リストを4つの表で繰り返しており、
縦に長いうえ「何を判定したか」と「なぜか」が同じ重さで並んでいました。

**人手と履歴が何を足したかを見せる。** モデルが最初に出した判定と違う場合 —— レビュアーが上書きした、
あるいは IME リストや過去症例が調整した場合 —— 元の判定を打ち消し線で併記し、調整の一覧を由来つきで表示します。
「前」の判定は**1回の実行**から復元しています（`InfluenceItem.from_verdict`）。
ベースラインを取るために再実行すると LLM の実行ごとのばらつきが混ざり、効果を分離できなくなるためで、
これは評価ハーネスで確立した考え方と同じです。

**症例ビルダー。** 固定サンプルは「動くこと」は示せても「気になるケースでどう振る舞うか」は示せないため、
制約付きの項目から症例を組み立てられるようにしました。クライアントが送るのは項目だけで、文書は送りません
（**BFF がサーバー側で報告書テキストを生成**）。これが下記のデモ保護と両立できる理由です。

**デモ保護。** 公開デモは有料APIを呼ぶため、入力を同梱サンプルとビルダー作成症例に限定し
（**サーバー側で強制**。ファイル選択UIを隠すだけでは API を直接叩かれて突破されます）、
IP単位と全体1日単位でレート制限をかけ、API は BFF からの共有シークレットを要求します。
その背後に、LLM プロバイダ側のハードな支出上限を置いています —— 絶対的な保証はこれだけです。

### 既知の制約（現MVP）

- 密ベクトル検索は、共通の書式・語彙を持つ文書間で混同しやすく、固有名詞（薬剤名・報告者名の区別等）に弱い傾向があります。ハイブリッド検索をロードマップに記載。
- トークンベースのチャンク化は日本語で文字の途中で分割されうるため、チャンク単位の文字オフセットはベストエフォートです（メタデータのみで、検索・回答には影響しません）。日本語対応スプリッタはPhase 5の改善項目。
- フロントエンドの自動テストは未整備（バックエンドは74件、大半がAPI非依存のフェイク）。手書きのTypeScript型とOpenAPIスキーマの契約テスト、およびE2Eスモークテストが次の追加候補。
- エラー処理はMVPとしてfail-fast。本番向けの堅牢化（リトライ、レート制限対応、構造化エラー）は今後。

### データについて

`data/sample_reports/` のサンプルは本プロジェクト用に作成した **合成** ICSRであり、実際の患者データは含みません。MedDRAサンプルは説明用の小さな部分集合です（完全なMedDRA用語はライセンス対象のため）。
