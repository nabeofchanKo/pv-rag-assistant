# PV RAG Assistant

**A retrieval-augmented assistant for pharmacovigilance (PV) — grounding every answer in the source safety report.**
**医薬品安全性監視（PV）業務のための、根拠提示型 RAG アシスタント。すべての回答を出典に紐づけます。**

🌐 **[English](#english)** ｜ **[日本語](#日本語)**

> **Status / 状況:** Active development. MVP complete (end-to-end RAG on Japanese ICSRs, built on LangChain). Evolving from a Q&A tool toward a PV triage / first-pass evaluation assistant — see the [Roadmap](#roadmap).

---

<a name="english"></a>
## English

A Retrieval-Augmented Generation (RAG) application specialized for **pharmacovigilance (PV)** — the practice of monitoring and assessing adverse drug reactions. It ingests Individual Case Safety Reports (ICSRs) and answers natural-language questions about reported adverse events, grounding every answer in the source documents with a citation.

This project is both a **portfolio piece** and a **learning vehicle**: the goal is not only a working app, but a system whose every design choice I can explain. It was first built from scratch on vendor SDKs to understand each RAG step, then migrated to LangChain for velocity (see [Design decisions](#design-decisions)).

### Why pharmacovigilance?

In drug-safety operations, the cost of a hallucinated or unsourced answer is high — incorrect adverse-event information has real clinical and regulatory consequences. This project treats **source traceability** and **hallucination resistance** as first-class design constraints, not afterthoughts. The domain was chosen to align with prior professional experience in pharmacovigilance (adverse-event evaluation and bilingual JP/EN regulatory documentation).

### What it does

- **Ingest** — Upload a PV report (PDF). The system extracts text per page, normalizes it (NFKC), splits it into overlapping token-based chunks, embeds each chunk, and stores it in a vector database.
- **Ask** — Submit a natural-language question. The system embeds the question, retrieves the most relevant chunks, and generates an answer constrained to the retrieved context.
- **Trace** — Every answer is returned with its source chunks (document name and page number), so it can be verified against the original report.

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

The pipeline is exposed via a **FastAPI** backend and consumed by a **Streamlit** frontend over HTTP, keeping frontend and backend cleanly separated. Both the embedding model and the chat model are injected as swappable LangChain abstractions, so they can be exchanged (e.g. for local models) without touching the pipeline.

### Tech stack

| Layer               | Choice                                             |
| ------------------- | -------------------------------------------------- |
| RAG orchestration   | LangChain 1.x (LCEL)                               |
| Backend API         | FastAPI                                            |
| Frontend            | Streamlit                                          |
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
├── frontend/
│   └── app.py                 # Streamlit UI
├── data/
│   ├── sample_reports/        # synthetic Japanese ICSRs (.txt source + .pdf)
│   └── meddra_sample/         # sample MedDRA subset (for upcoming MedDRA features)
├── .env.example
└── README.md
```

### Getting started

**Prerequisites:** Python 3.12+ and an OpenAI API key.

```bash
git clone https://github.com/nabeofchanKo/pv-rag-assistant.git
cd pv-rag-assistant

python -m venv venv
source venv/bin/activate         # macOS/Linux
# source venv/Scripts/activate   # Windows (Git Bash)

pip install -r backend/requirements.txt

cp .env.example .env
# then edit .env and set OPENAI_API_KEY
```

Run the backend and frontend as two processes:

```bash
# Terminal 1 — backend (from project root)
cd backend
uvicorn app.main:app --reload
# API docs at http://localhost:8000/docs

# Terminal 2 — frontend
cd frontend
streamlit run app.py
# UI at http://localhost:8501
```

Upload a PDF from `data/sample_reports/`, then ask a question about its contents.

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
- [ ] **Phase 6 — Frontend & deployment:** Next.js frontend, containerization, deploy to AWS.

### Design note — expectedness (既知/未知)

Expectedness (is an adverse event already described in the drug's package insert?) is implemented as **Approach A: RAG retrieval over the insert text.** The package insert is chunked and embedded; for each adverse event we retrieve the most relevant "副作用" (adverse-reaction) passages of that drug's insert and an LLM judges *listed (既知)* / *not listed (未知)* / *undetermined*, returning the cited passage as evidence. This reuses the existing retrieval stack and keeps the judgment grounded, with **未知 as the safe default** when no supporting passage is found.

**Future extension — Approach C (hybrid, to A/B test):** read each insert *once* with an LLM to extract its adverse-reaction section into a structured, source-cited ADR list, cache it, then match each adverse event against that list. This trades per-query retrieval for a deterministic, auditable list (closer in spirit to the deterministic product-master matching). Worth benchmarking against Approach A on accuracy × cost once Approach A is in place.

### Design note — local embedding tier (Phase 5a)

The **cost / privacy ladder** now has its first local rung. `get_embeddings()` dispatches on `EMBEDDING_PROVIDER` — `openai` (default) or `ollama`, a local model (e.g. `bge-m3`) served by Ollama so case text never leaves the machine. Because a vector store is bound to one embedding dimension, the Chroma store is namespaced per embedding model, so both providers coexist and switching is a flag flip (the reference collections re-index at startup). A deterministic, LLM-free [retrieval bench](experiments/embedding_retrieval_bench.md) shows local `bge-m3` matches OpenAI `text-embedding-3-small` on the retrieval the system actually uses (hybrid hit@3 = 100% on both; the only gap is one term at vector-only rank-1, absorbed by the BM25/exact fusion), and an end-to-end run keeps the under-call-0 safety invariant. Local's win is privacy + zero marginal cost + no quota, **not** latency (LangChain's Ollama embedder is sequential, so per-query it is slower here). OpenAI stays the default; local is a validated opt-in. See [ADR 0011](docs/adr/0011-local-embedding-provider.md).

### Design note — local generation, per step (Phase 5b)

Generation is swappable the same way (`CHAT_PROVIDER=ollama`, one `OLLAMA_CHAT_MODEL` for every step). Because a full end-to-end triage on a local 7B is impractical (~10-15 min/case), a [per-step comparison harness](experiments/scripts/generation_bench.py) benchmarks each step in isolation over the gold set — which is also exactly the "where does local hold vs break" question — reporting **under-calls first**. Across OpenAI vs qwen2.5:7b / ELYZA-JP-8B / gemma3:4b / medllama2, the [result](experiments/generation_comparison.md) is clear: **no local 7-8B preserves the under-call-0 safety invariant** — every one misses a serious event on the hard-narrative seriousness step. **ELYZA-JP-8B is the strongest local** (extraction 91%, beating OpenAI's 87%; MedDRA and causality 100%) and is viable for extraction / coding / the conservative causality default, but the safety-critical judgments still need the frontier model. The honest cost×privacy answer is therefore **hybrid per-step** — local for the easy/deterministic steps, OpenAI for the three judgment axes. The Ollama path is hardened (`num_ctx`/`num_predict`/timeout) so a local model can't run away or hang the pipeline. See [ADR 0012](docs/adr/0012-local-generation-per-step.md).

### Known limitations (current MVP)

- Dense-vector retrieval can be confused by documents that share a common format/vocabulary, and is weaker on proper nouns (e.g. distinguishing one drug or reporter name from another). Hybrid retrieval is on the roadmap.
- Token-based chunking can split mid-character on Japanese text, so per-chunk character offsets are best-effort (they are metadata only and do not affect retrieval or answers). A Japanese-aware splitter is a Phase 5 improvement.
- Automated tests are minimal so far; correctness has been verified end-to-end (including live OpenAI calls).
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

- **取り込み** — PV報告書（PDF）をアップロード。ページ単位でテキスト抽出→正規化（NFKC）→トークンベースで重複ありチャンク化→埋め込み→ベクトルDBに保存。
- **質問** — 自然言語で質問。質問を埋め込み、関連チャンクを検索し、**検索結果の文脈のみに基づいて**回答を生成。
- **追跡** — 回答は必ず出典チャンク（文書名・ページ番号）付きで返るため、元report と照合・検証できます。

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

パイプラインは **FastAPI** バックエンドとして公開し、**Streamlit** フロントエンドが HTTP 経由で利用します（フロント／バックの分離）。埋め込みモデルとチャットモデルは、差し替え可能な LangChain の抽象として注入されるため、パイプラインを触らずに（例：ローカルモデルへ）交換できます。

### 技術スタック

| レイヤー             | 採用                                                 |
| -------------------- | ---------------------------------------------------- |
| RAG オーケストレーション | LangChain 1.x（LCEL）                             |
| バックエンドAPI      | FastAPI                                              |
| フロントエンド       | Streamlit                                           |
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
├── frontend/
│   └── app.py                 # Streamlit UI
├── data/
│   ├── sample_reports/        # 合成の日本語ICSR（.txt原本＋.pdf）
│   └── meddra_sample/         # MedDRAサンプル部分集合（今後のMedDRA機能用）
├── .env.example
└── README.md
```

### セットアップ

**前提:** Python 3.12以上、OpenAI APIキー。

```bash
git clone https://github.com/nabeofchanKo/pv-rag-assistant.git
cd pv-rag-assistant

python -m venv venv
source venv/bin/activate         # macOS/Linux
# source venv/Scripts/activate   # Windows (Git Bash)

pip install -r backend/requirements.txt

cp .env.example .env
# .env を編集し OPENAI_API_KEY を設定
```

バックエンドとフロントエンドは2プロセスで起動します。

```bash
# ターミナル1 — バックエンド（プロジェクトルートから）
cd backend
uvicorn app.main:app --reload
# APIドキュメント: http://localhost:8000/docs

# ターミナル2 — フロントエンド
cd frontend
streamlit run app.py
# UI: http://localhost:8501
```

`data/sample_reports/` のPDFをアップロードし、内容について質問してください。

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
- [ ] **Phase 6 — フロントエンド・デプロイ:** Next.js フロントエンド、コンテナ化、AWSへデプロイ。

### 設計メモ — 既知／未知判定（expectedness）

既知／未知（その有害事象が添付文書に記載済みか）は **Approach A：添付文書テキストへの RAG 検索** で実装します。添付文書をチャンク化・埋め込みし、有害事象ごとに当該薬剤の「副作用」欄の関連箇所を検索して、LLM が *記載あり（既知）／記載なし（未知）／判定不能* を判定し、根拠となる引用文を返します。既存の検索基盤を再利用し、根拠に紐づけた判定を行います。裏付けとなる記載が見つからない場合は **未知を安全側の既定値** とします。

**今後の拡張 — Approach C（ハイブリッド、A/B比較の候補）:** 添付文書を **一度だけ** LLM で読み、副作用欄を出典付きの構造化 ADR リストへ抽出してキャッシュし、以後は各有害事象をそのリストと照合する方式。クエリごとの検索を、決定的で監査可能なリストに置き換える（決定的な自社品マスタ照合に思想が近い）。Approach A の実装後、精度×コストでベンチマークする価値がある。

### 設計メモ — ローカル埋め込みティア（Phase 5a）

**コスト／プライバシーの梯子** に最初のローカル段を追加しました。`get_embeddings()` は `EMBEDDING_PROVIDER` で分岐し、`openai`（既定）または `ollama`（Ollama が配信するローカルモデル、例 `bge-m3`）を選べます。後者では症例テキストが端末外に出ません。ベクトルストアは埋め込み次元に紐づくため、Chroma ストアを埋め込みモデル単位で名前空間分離し、両プロバイダを共存させてフラグ一つで切替可能にしています（参照コレクションは起動時に再インデックス）。決定的・LLM非依存の [検索ベンチ](experiments/embedding_retrieval_bench.md) では、ローカル `bge-m3` が実運用で使う検索（hybrid hit@3＝両者100%。差は vector単独のrank-1で1件のみで、BM25/exact融合が吸収）で OpenAI `text-embedding-3-small` と同等、end-to-end でも過小コール0の安全インバリアントを維持しました。ローカルの利点はプライバシー＋限界コスト0＋クォータ無しで、**レイテンシではありません**（LangChain の Ollama 埋め込みは逐次実行のため単発クエリはむしろ遅い）。既定は OpenAI のまま、ローカルは検証済みのオプトイン。[ADR 0011](docs/adr/0011-local-embedding-provider.md) 参照。

### 設計メモ — ローカル生成、ステップ別（Phase 5b）

生成も同様に差し替え可能です（`CHAT_PROVIDER=ollama`、全ステップを1つの `OLLAMA_CHAT_MODEL` で実行）。ローカル7BでのフルE2Eは約10-15分/症例と非現実的なため、[ステップ別比較ハーネス](experiments/scripts/generation_bench.py)で各ステップを分離計測し（＝「どこでローカルが持つ/崩れるか」の問いに直結）、**過小コールを最優先**で報告します。OpenAI vs qwen2.5:7b / ELYZA-JP-8B / gemma3:4b / medllama2 の[結果](experiments/generation_comparison.md)は明快で、**7-8Bのローカル勢はどれも過小コール0の安全インバリアントを保てません** — 全モデルが hard-narrative の重篤度で重篤事象を見落とします。**ELYZA-JP-8B が最良のローカル**（抽出91%でOpenAIの87%を上回り、MedDRA・因果は100%）で、抽出／コード化／保守的な因果既定には実用ですが、安全critな判定はやはり frontier モデルが必要です。よって正直なコスト×プライバシーの答えは **ステップ別ハイブリッド** — 簡単／決定的なステップはローカル、3つの判定軸はOpenAI。Ollama経路は暴走・ハングを防ぐよう `num_ctx`/`num_predict`/タイムアウトで堅牢化しています。[ADR 0012](docs/adr/0012-local-generation-per-step.md) 参照。

### 既知の制約（現MVP）

- 密ベクトル検索は、共通の書式・語彙を持つ文書間で混同しやすく、固有名詞（薬剤名・報告者名の区別等）に弱い傾向があります。ハイブリッド検索をロードマップに記載。
- トークンベースのチャンク化は日本語で文字の途中で分割されうるため、チャンク単位の文字オフセットはベストエフォートです（メタデータのみで、検索・回答には影響しません）。日本語対応スプリッタはPhase 5の改善項目。
- 自動テストはまだ最小限で、正しさはエンドツーエンド（OpenAIへの実通信を含む）で確認済み。
- エラー処理はMVPとしてfail-fast。本番向けの堅牢化（リトライ、レート制限対応、構造化エラー）は今後。

### データについて

`data/sample_reports/` のサンプルは本プロジェクト用に作成した **合成** ICSRであり、実際の患者データは含みません。MedDRAサンプルは説明用の小さな部分集合です（完全なMedDRA用語はライセンス対象のため）。
