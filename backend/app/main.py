import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.dependencies import get_label_index_service, get_meddra_retriever
from app.routers import cases, documents, query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Index the reference corpora once (idempotent: only when a collection is empty).
    # Failures are non-fatal so the rest of the API still starts.
    try:
        added = get_label_index_service().ensure_indexed()
        if added:
            logger.info("Indexed %d drug-label chunks at startup.", added)
    except Exception:  # noqa: BLE001 - startup indexing must never crash the app
        logger.exception("Drug-label indexing failed at startup; expectedness disabled.")
    try:
        added = get_meddra_retriever().ensure_indexed()
        if added:
            logger.info("Indexed %d MedDRA PTs at startup.", added)
    except Exception:  # noqa: BLE001
        logger.exception("MedDRA indexing failed at startup; coding disabled.")
    yield


app = FastAPI(title="PV RAG Assistant", version="0.1.0", lifespan=lifespan)

# Optional shared secret with the BFF (Phase 6 / ADR 0013). When deployed, the
# API and the Next.js app are separate App Runner services, each with a public
# URL — so without this the API would be callable directly, bypassing the BFF's
# rate limiting and sample-only policy. Unset (local dev, compose) = disabled,
# so nothing changes for a developer running the stack.
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN")

# Paths reachable without the token: the health route App Runner probes, and the
# generated API docs.
_OPEN_PATHS = frozenset({"/", "/docs", "/openapi.json", "/redoc"})


@app.middleware("http")
async def require_internal_token(request: Request, call_next):
    if INTERNAL_API_TOKEN and request.url.path not in _OPEN_PATHS:
        supplied = request.headers.get("x-internal-token", "")
        # Constant-time compare so a wrong token cannot be guessed by timing.
        if not secrets.compare_digest(supplied, INTERNAL_API_TOKEN):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return await call_next(request)

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(cases.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "PV RAG Assistant"}