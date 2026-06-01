import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.dependencies import (
    get_chunker,
    get_embedding_service,
    get_pdf_processor,
    get_retriever_service,
)
from app.schemas import UploadResponse
from app.services.chunking import FixedLengthChunker
from app.services.embedding import EmbeddingService
from app.services.pdf_processor import PDFProcessor
from app.services.retriever import RetrieverService

router = APIRouter()


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_endpoint(
    file: UploadFile = File(...),
    pdf_processor: PDFProcessor = Depends(get_pdf_processor),
    chunker: FixedLengthChunker = Depends(get_chunker),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    retriever: RetrieverService = Depends(get_retriever_service),
) -> UploadResponse:
    """Upload a PDF, index it, and store chunks in the vector store."""

    contents = await file.read()
    
    filename = file.filename or "uploaded.pdf"
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / filename
    tmp_path.write_bytes(contents)
    
    try:
        doc = pdf_processor.process(tmp_path)
        chunks = chunker.chunk_document(doc)
        embedded = embedding_service.embed_chunks(chunks)
        retriever.add_chunks(embedded)
    finally:
        tmp_path.unlink()      # ファイル削除
        tmp_dir.rmdir()        # ディレクトリ削除

    return UploadResponse(
        document_name=filename,
        chunks_added=len(chunks),
        message=f"Successfully uploaded {len(chunks)} chunks."
    )