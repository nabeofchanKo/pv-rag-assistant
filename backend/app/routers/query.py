from fastapi import APIRouter, Depends

from app.dependencies import (
    get_generator_service,
    get_retriever_service,
)
from app.schemas import QueryRequest, QueryResponse, SourceInfo
from app.services.generator import GeneratorService
from app.services.retriever import RetrieverService

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query_endpoint(
    request: QueryRequest,
    retriever: RetrieverService = Depends(get_retriever_service),
    generator: GeneratorService = Depends(get_generator_service),
) -> QueryResponse:
    """Handle a RAG query: retrieve relevant chunks and generate an answer."""

    chunks = retriever.search(query=request.query, top_k=request.top_k)
    rag_response = generator.generate(query=request.query, chunks=chunks)

    sources = []
    for chunk in rag_response.source_chunks:
        source_info = SourceInfo(
            document_name=chunk.document_name,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
        )
        sources.append(source_info)

    return QueryResponse(
        answer=rag_response.answer,
        query=rag_response.query,
        sources=sources,
    )
