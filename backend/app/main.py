import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.dependencies import get_label_index_service
from app.routers import cases, documents, query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Index the drug labels (添付文書) once for expectedness (既知/未知). Idempotent:
    # only runs when the label collection is empty. Failure is non-fatal so the
    # rest of the API still starts (expectedness just returns 判定不能).
    try:
        added = get_label_index_service().ensure_indexed()
        if added:
            logger.info("Indexed %d drug-label chunks at startup.", added)
    except Exception:  # noqa: BLE001 - startup indexing must never crash the app
        logger.exception("Drug-label indexing failed at startup; expectedness disabled.")
    yield


app = FastAPI(title="PV RAG Assistant", version="0.1.0", lifespan=lifespan)

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(cases.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "PV RAG Assistant"}