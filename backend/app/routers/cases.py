import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.dependencies import (
    get_extraction_service,
    get_ingestion_service,
    get_product_master_service,
)
from app.exceptions import IngestionError, UnsupportedFileTypeError
from app.schemas import TriageResponse
from app.services.extraction import ExtractionService
from app.services.ingestion import IngestionService
from app.services.product_master import ProductMasterService

router = APIRouter()


@router.post("/cases/triage", response_model=TriageResponse)
async def triage_endpoint(
    file: UploadFile = File(...),
    ingestion: IngestionService = Depends(get_ingestion_service),
    extraction: ExtractionService = Depends(get_extraction_service),
    product_master: ProductMasterService = Depends(get_product_master_service),
) -> TriageResponse:
    """Ingest a case (PDF / email / image / text) and return a triage draft:
    own-company product match + structured patient / adverse-event extraction."""

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

        text = doc.full_text
        product_match = product_master.match(text)
        case_extraction = extraction.extract(text)
    finally:
        tmp_path.unlink()      # remove the temp file
        tmp_dir.rmdir()        # remove the temp directory

    return TriageResponse(
        document_name=filename,
        product_match=product_match,
        extraction=case_extraction,
        source_text=text,
    )
