import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.dependencies import (
    get_chunker,
    get_ingestion_service,
    get_retriever_service,
)
from app.exceptions import IngestionError, UnsupportedFileTypeError
from app.schemas import UploadResponse
from app.services.chunking import FixedLengthChunker
from app.services.ingestion import IngestionService
from app.services.retriever import RetrieverService

router = APIRouter()


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_endpoint(
    file: UploadFile = File(...),
    ingestion: IngestionService = Depends(get_ingestion_service),
    chunker: FixedLengthChunker = Depends(get_chunker),
    retriever: RetrieverService = Depends(get_retriever_service),
) -> UploadResponse:
    """Upload a document (PDF / email / text), index it, and store its chunks."""

    contents = await file.read()

    filename = file.filename or "uploaded"
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / filename
    tmp_path.write_bytes(contents)

    try:
        try:
            doc = ingestion.load(tmp_path)
        except UnsupportedFileTypeError as e:
            raise HTTPException(status_code=415, detail=str(e))
        except IngestionError as e:
            raise HTTPException(status_code=422, detail=str(e))

        chunks = chunker.chunk_document(doc)
        retriever.add_chunks(chunks)
    finally:
        tmp_path.unlink()      # remove the temp file
        tmp_dir.rmdir()        # remove the temp directory

    return UploadResponse(
        document_name=filename,
        chunks_added=len(chunks),
        message=f"Successfully uploaded {len(chunks)} chunks."
    )
