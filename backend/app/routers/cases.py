import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from langgraph.graph.state import CompiledStateGraph

from app.dependencies import get_ingestion_service, get_triage_graph
from app.exceptions import IngestionError, UnsupportedFileTypeError
from app.schemas import TriageResponse
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post("/cases/triage", response_model=TriageResponse)
async def triage_endpoint(
    file: UploadFile = File(...),
    ingestion: IngestionService = Depends(get_ingestion_service),
    graph: CompiledStateGraph = Depends(get_triage_graph),
) -> TriageResponse:
    """Ingest a case (PDF / email / image / text) and return a triage draft:
    own-company product match + structured patient / adverse-event extraction +
    MedDRA PT + seriousness (ICH E2A) + causality (temporal) + expectedness (既知/未知).

    Ingestion (file → text) and HTTP error mapping stay here at the boundary;
    the six evaluation steps run inside the LangGraph triage graph (Phase 4a)."""

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
    finally:
        tmp_path.unlink()      # remove the temp file
        tmp_dir.rmdir()        # remove the temp directory

    # Run the orchestrated triage pipeline (product match → extraction → MedDRA →
    # seriousness / causality / expectedness) and assemble the response.
    final = graph.invoke({"text": text, "document_name": filename})

    return TriageResponse(
        document_name=filename,
        product_match=final["product_match"],
        extraction=final["extraction"],
        meddra=final.get("meddra", []),
        seriousness=final.get("seriousness", []),
        causality=final.get("causality", []),
        expectedness=final.get("expectedness", []),
        source_text=text,
    )
