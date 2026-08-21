import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(cases.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "PV RAG Assistant"}