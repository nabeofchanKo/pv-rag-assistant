import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.dependencies import (
    get_ime_reference,
    get_ingestion_service,
    get_precedent_service,
    get_triage_graph,
)
from app.exceptions import IngestionError, UnsupportedFileTypeError
from app.schemas import (
    ImePromotionRecord,
    OutOfScopeResult,
    ReviewDecision,
    TriageDraft,
    TriageResult,
)
from app.services.ime import ImeReference
from app.services.ingestion import IngestionService
from app.services.precedent import PrecedentService, record_from_result
from app.services.triage_graph import ALLOWED_VERDICTS, compute_escalations

router = APIRouter()


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _content_fields(values: dict) -> dict:
    """The shared TriageResponse fields, read from a graph state snapshot."""
    return dict(
        document_name=values.get("document_name", ""),
        product_match=values["product_match"],
        extraction=values["extraction"],
        meddra=values.get("meddra", []),
        seriousness=values.get("seriousness", []),
        causality=values.get("causality", []),
        expectedness=values.get("expectedness", []),
        precedent=values.get("precedent", []),
        influence_mode=values.get("influence_mode", "applied"),
        influence=values.get("influence", []),
        source_text=values.get("text", ""),
    )


def _out_of_scope(thread_id: str, values: dict) -> OutOfScopeResult:
    return OutOfScopeResult(
        thread_id=thread_id,
        product_match=values["product_match"],
        source_text=values.get("text", ""),
    )


def _draft(thread_id: str, values: dict) -> TriageDraft:
    return TriageDraft(
        thread_id=thread_id,
        escalations=compute_escalations(
            values.get("seriousness", []),
            values.get("causality", []),
            values.get("expectedness", []),
            values.get("precedent", []),
        ),
        **_content_fields(values),
    )


def _result(thread_id: str, values: dict) -> TriageResult:
    return TriageResult(
        thread_id=thread_id,
        status=values["status"],
        review=values["review_outcome"],
        **_content_fields(values),
    )


@router.post("/cases/triage", response_model=None)
async def triage_endpoint(
    file: UploadFile = File(...),
    auto_approve: bool = False,
    influence: str = "applied",
    ingestion: IngestionService = Depends(get_ingestion_service),
    graph: CompiledStateGraph = Depends(get_triage_graph),
) -> TriageDraft | TriageResult | OutOfScopeResult:
    """Ingest a case (PDF / email / image / text) and start a triage run.

    The six evaluation steps run inside the LangGraph triage graph, which then
    pauses at a human-review gate and returns a **draft** (status
    ``awaiting_review``) plus a ``thread_id`` — approve/reject it via
    ``POST /cases/{thread_id}/approve``. Pass ``?auto_approve=true`` to skip the
    human gate and run straight through (non-HITL / batch use).

    Ingestion (file → text) and HTTP error mapping stay here at the boundary."""

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

    thread_id = str(uuid.uuid4())
    graph.invoke(
        {
            "text": text,
            "document_name": filename,
            "auto_approve": auto_approve,
            "influence_mode": "advisory" if influence == "advisory" else "applied",
        },
        _config(thread_id),
    )
    values = graph.get_state(_config(thread_id)).values

    if values.get("status") == "out_of_scope":  # no own-company product → hard-gated
        return _out_of_scope(thread_id, values)
    if values.get("status"):  # auto_approve ran the review gate straight through
        return _result(thread_id, values)
    return _draft(thread_id, values)


@router.get("/cases/{thread_id}", response_model=None)
async def get_case(
    thread_id: str,
    graph: CompiledStateGraph = Depends(get_triage_graph),
) -> TriageDraft | TriageResult | OutOfScopeResult:
    """Reload a triage run by thread id — its draft (awaiting review) or its
    finalized result. Backed by the checkpointer, so it survives restarts."""
    snapshot = graph.get_state(_config(thread_id))
    values = snapshot.values
    if not values:
        raise HTTPException(status_code=404, detail=f"unknown thread_id: {thread_id}")
    if values.get("status") == "out_of_scope":
        return _out_of_scope(thread_id, values)
    if values.get("status"):
        return _result(thread_id, values)
    return _draft(thread_id, values)


@router.post("/cases/{thread_id}/approve", response_model=None)
async def approve_case(
    thread_id: str,
    decision: ReviewDecision,
    graph: CompiledStateGraph = Depends(get_triage_graph),
    ime: ImeReference = Depends(get_ime_reference),
    precedent: PrecedentService = Depends(get_precedent_service),
) -> TriageResult:
    """Resume a paused triage run with the reviewer's decision.

    On ``approve`` the reviewer's verdict overrides are applied and an audit
    trail (original → new verdict) is recorded; any IME promotions grow the
    important-medical-events list so future cases with that PT fire E2A
    criterion 6 automatically (Phase 4c). On ``reject`` the draft is left
    unchanged and marked rejected. Returns the finalized result."""
    snapshot = graph.get_state(_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"unknown thread_id: {thread_id}")
    if not snapshot.next:  # already finalized (no pending human_review task)
        raise HTTPException(
            status_code=409,
            detail=f"thread {thread_id} is already {snapshot.values.get('status')}",
        )

    # Validate overrides against the allowed verdicts for each axis.
    for ov in decision.overrides:
        allowed = ALLOWED_VERDICTS.get(ov.axis)
        if allowed is None:
            raise HTTPException(status_code=422, detail=f"unknown axis: {ov.axis}")
        if ov.new_verdict not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"{ov.axis} の判定は {sorted(allowed)} のいずれか（受領: {ov.new_verdict}）",
            )
    # Validate IME promotions (need a real coded PT to key criterion 6 on).
    for p in decision.ime_promotions:
        if not p.pt_code.strip():
            raise HTTPException(
                status_code=422, detail="IME昇格には pt_code（コード化済みPT）が必要です。"
            )
    # Validate manual added-event verdicts against the allowed values.
    for ev in decision.added_events:
        if ev.seriousness not in ALLOWED_VERDICTS["seriousness"]:
            raise HTTPException(status_code=422, detail=f"追加事象の重篤度が不正: {ev.seriousness}")
        if ev.causality not in ALLOWED_VERDICTS["causality"]:
            raise HTTPException(status_code=422, detail=f"追加事象の因果が不正: {ev.causality}")

    # Perform the IME promotions (approve only) — a reference-side effect done at
    # the boundary, then recorded in the audit trail via the resume payload.
    payload = decision.model_dump()
    promotion_records: list[ImePromotionRecord] = []
    if decision.action == "approve":
        when = datetime.now()
        for p in decision.ime_promotions:
            note = f"HITL昇格 {decision.reviewer} {when:%Y-%m-%d}"
            if p.rationale:
                note += f" — {p.rationale}"
            added = ime.promote(p.pt_code, p.pt_name, note)
            promotion_records.append(
                ImePromotionRecord(
                    pt_code=p.pt_code, pt_name=p.pt_name, reviewer=decision.reviewer,
                    promoted_at=when, rationale=p.rationale,
                    status="追加" if added else "既存",
                )
            )
    payload["ime_promotion_records"] = [r.model_dump() for r in promotion_records]

    graph.invoke(Command(resume=payload), _config(thread_id))
    values = graph.get_state(_config(thread_id)).values
    result = _result(thread_id, values)

    # An approved case becomes precedent for future triage (Phase 4d).
    if result.status == "approved":
        precedent.save(record_from_result(result))

    return result
