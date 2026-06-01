from fastapi import FastAPI

from app.routers import documents, query


app = FastAPI(title="PV RAG Assistant", version="0.1.0")

app.include_router(documents.router)
app.include_router(query.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "PV RAG Assistant"}