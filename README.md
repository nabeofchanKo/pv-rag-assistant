# PV RAG Assistant

A Retrieval-Augmented Generation (RAG) application specialized for **pharmacovigilance (PV)** — the practice of monitoring and assessing adverse drug reactions. The system ingests Individual Case Safety Reports (ICSRs) in PDF format and answers natural-language questions about reported adverse events, grounding every answer in the source documents.

> **Status: Active development (MVP complete).** The core RAG pipeline, REST API, and a minimal web UI are working end-to-end. Domain-specific features, retrieval evaluation, containerization, and cloud deployment are on the roadmap below.

## Why pharmacovigilance?

In drug-safety operations, the cost of a hallucinated or unsourced answer is high — incorrect adverse-event information has real clinical and regulatory consequences. This project treats **source traceability** and **hallucination resistance** as first-class design constraints rather than afterthoughts, which shapes several decisions documented below.

This domain was chosen to align with prior professional experience in pharmacovigilance (adverse event evaluation and bilingual JP/EN regulatory documentation).

## What it does

- **Ingest**: Upload a PV report (PDF). The system extracts text per page, splits it into overlapping token-based chunks, embeds each chunk, and stores it in a vector database.
- **Ask**: Submit a natural-language question. The system embeds the question, retrieves the most relevant chunks, and generates an answer constrained to the retrieved context.
- **Trace**: Every answer is returned with its source chunks (document name and page number), so the answer can be verified against the original report.

## Demo

The Streamlit UI supports document upload and question answering. Uploaded documents become immediately searchable.

Example: after uploading an ICSR for "DrugY", asking *"What adverse events were reported for DrugY?"* returns a structured list of events (hepatic function abnormal, jaundice, fatigue, etc.) with the source report and page cited. Out-of-context questions correctly return *"The provided context does not contain this information."*

## Architecture

```
PDF upload
    │
    ▼
PDFProcessor      ── extracts text per page (pdfplumber), normalizes (NFKC)
    │
    ▼
FixedLengthChunker ── token-based chunking (tiktoken), 500 tokens / 100 overlap
    │                  implemented behind a ChunkingStrategy interface
    ▼
EmbeddingService  ── OpenAI text-embedding-3-small, batched requests
    │
    ▼
RetrieverService  ── ChromaDB (cosine similarity), stores & searches chunks
    │
    ▼
GeneratorService  ── OpenAI gpt-4o-mini, context-grounded answer generation
    │
    ▼
RAGResponse       ── answer + source chunks
```

The pipeline is exposed via a **FastAPI** backend and consumed by a **Streamlit** frontend over HTTP, keeping frontend and backend cleanly separated.

## Tech stack

| Layer           | Choice                          |
| --------------- | ------------------------------- |
| Backend API     | FastAPI                         |
| Frontend        | Streamlit                       |
| PDF parsing     | pdfplumber                      |
| Tokenization    | tiktoken (cl100k_base)          |
| Embeddings      | OpenAI `text-embedding-3-small` |
| Vector store    | ChromaDB (persistent, cosine)   |
| Generation      | OpenAI `gpt-4o-mini`            |
| Data validation | Pydantic v2                     |
| Config          | pydantic-settings               |

## Design decisions

A few deliberate choices that shaped the implementation:

- **Direct SDKs over an orchestration framework.** The RAG pipeline is built directly on the OpenAI and ChromaDB SDKs rather than a higher-level framework. This keeps the data flow explicit and every step inspectable — important for a domain where understanding *why* a particular chunk was retrieved matters.
- **Strategy pattern for chunking.** Chunking is implemented behind an abstract `ChunkingStrategy` interface, with `FixedLengthChunker` as the first concrete strategy. This makes it straightforward to add and compare alternative strategies (planned in the roadmap) without touching calling code.
- **Immutable domain models.** Domain objects (`Chunk`, `ProcessedDocument`, etc.) are frozen Pydantic models, making processing results safe to pass around and reason about.
- **Dependency injection throughout.** Services receive their clients (OpenAI, ChromaDB) via injection, and FastAPI endpoints receive services via `Depends`, which keeps construction logic in one place and makes the system testable.
- **Hallucination guardrails.** Generation uses `temperature=0` and a system prompt that constrains answers to the provided context and instructs the model to decline when information is absent. The internal `Chunk` model is mapped to a separate public `SourceInfo` model so API responses expose only what is needed.
- **Source traceability.** Page numbers are preserved from extraction through to the final response, so every answer can cite the document and page it came from.

## Project structure

```
pv-rag-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── config.py          # settings via pydantic-settings
│   │   ├── dependencies.py    # DI providers for services and clients
│   │   ├── exceptions.py      # custom PDF-processing exceptions
│   │   ├── schemas.py         # Pydantic domain & API models
│   │   ├── routers/
│   │   │   ├── documents.py   # POST /documents/upload
│   │   │   └── query.py       # POST /query
│   │   └── services/
│   │       ├── pdf_processor.py  # PDF text extraction
│   │       ├── chunking.py       # ChunkingStrategy + FixedLengthChunker
│   │       ├── embedding.py      # OpenAI embeddings
│   │       ├── retriever.py      # ChromaDB store & search
│   │       └── generator.py      # context-grounded generation
│   └── requirements.txt
├── frontend/
│   └── app.py                 # Streamlit UI
├── data/
│   ├── sample_reports/        # synthetic ICSR PDFs
│   └── meddra_sample/         # sample MedDRA dictionary (for upcoming MedDRA feature)
├── .env.example
└── README.md
```

## Getting started

### Prerequisites

- Python 3.12+
- An OpenAI API key

### Setup

```bash
# Clone and enter the project
git clone https://github.com/nabeofchanKo/pv-rag-assistant.git
cd pv-rag-assistant

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows (Git Bash)

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
# then edit .env and set OPENAI_API_KEY
```

### Run

The backend and frontend run as two processes.

```bash
# Terminal 1 — backend (from project root)
cd backend
uvicorn app.main:app --reload
# API docs available at http://localhost:8000/docs

# Terminal 2 — frontend
cd frontend
streamlit run app.py
# UI available at http://localhost:8501
```

Upload a PDF from `data/sample_reports/`, then ask a question about its contents.

## API

| Method | Endpoint            | Description                                          |
| ------ | ------------------- | ---------------------------------------------------- |
| `POST` | `/documents/upload` | Upload and index a PDF                               |
| `POST` | `/query`            | Ask a question; returns an answer with cited sources |
| `GET`  | `/`                 | Health check                                         |

Interactive API documentation is auto-generated at `/docs`.

## Note on data

The sample reports in `data/sample_reports/` are **synthetic** ICSRs created for this project; they contain no real patient data. The MedDRA sample dictionary is a small illustrative subset, as the full MedDRA terminology is licensed.

## Roadmap

- [x] **MVP**: end-to-end RAG (extract → chunk → embed → store → retrieve → generate), FastAPI API, Streamlit UI
- [ ] **PV domain features**: automated MedDRA term suggestion for adverse-event text
- [ ] **Retrieval evaluation**: compare chunking strategies and embedding models with Hit Rate@k / MRR; investigate hybrid (dense + keyword) retrieval to address dense-vector weaknesses on proper nouns
- [ ] **Multilingual support**: Japanese/English chunking and cross-lingual retrieval experiments
- [ ] **Quality & tooling**: unit/integration tests, ruff + mypy in CI
- [ ] **Containerization**: Docker Compose for local orchestration
- [ ] **Answer quality measurement**: RAGAS-style faithfulness / relevancy metrics
- [ ] **Deployment**: containerized deployment to AWS

## Known limitations (current MVP)

- Dense-vector retrieval can be confused by documents that share a common format/vocabulary, and is weaker on proper nouns (e.g. distinguishing one drug or reporter name from another). Addressing this with hybrid retrieval is on the roadmap.
- No automated tests yet; correctness has been verified manually end-to-end.
- Error handling is fail-fast (MVP); production hardening (retries, rate-limit handling, structured error responses) is planned.
