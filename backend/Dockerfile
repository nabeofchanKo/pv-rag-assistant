# syntax=docker/dockerfile:1
#
# PV RAG Assistant — backend (FastAPI + LangGraph) container image.
#
# Build context is the REPO ROOT (not backend/), because the app resolves
# PROJECT_ROOT to the repo root and reads reference data from ./data. Build with:
#
#   docker build -f backend/Dockerfile -t pv-rag-assistant-backend:local .
#
# Multi-stage: a builder installs dependencies into an isolated venv (with a
# compiler available for any sdist), and a slim runtime stage copies just the
# venv + app code + reference data — keeping the final image small and toolchain-free.

# ---- Stage 1: builder — resolve deps into /opt/venv ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential covers any dependency that ships without a manylinux wheel;
# it stays in this stage and never reaches the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Warm the tiktoken BPE vocab cache at BUILD time. tiktoken otherwise downloads
# these on first use (the first embedding call), which makes a runtime request to
# openaipublic.blob.core.windows.net — a network dependency we do not want in a
# running container, and one that fails outright behind a TLS-inspecting proxy
# whose CA certifi does not trust. Baking it in makes startup self-contained.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache
RUN mkdir -p "$TIKTOKEN_CACHE_DIR" \
    && python -c "import tiktoken; [tiktoken.get_encoding(e) for e in ('cl100k_base','o200k_base')]"

# ---- Stage 2: runtime — slim image, non-root ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/backend \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache

# Dedicated non-root runtime user.
RUN useradd --create-home --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/tiktoken_cache /opt/tiktoken_cache

# App code + read-only reference data. Copied so that config.py's
# PROJECT_ROOT (= this file's parent.parent.parent) resolves to /app,
# making ./data/... paths land on /app/data/...
COPY backend/app /app/backend/app
COPY data /app/data

# Writable runtime state, owned by the runtime user:
#   chroma_db    — vector index (rebuilt at startup if empty)
#   checkpoints  — LangGraph HITL interrupt/resume SQLite store
#   past_cases   — precedent records saved on approval
RUN mkdir -p /app/backend/chroma_db /app/backend/checkpoints /app/backend/past_cases \
    && chown -R appuser:appuser /app/backend

WORKDIR /app/backend
USER appuser

EXPOSE 8000

# Liveness: GET / returns {"status": "ok"}.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/').status==200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
