"""The triage routes' response models: documented, and harmless.

These routes used to declare ``response_model=None`` (they return a union), so
TriageDraft / TriageResult / OutOfScopeResult were absent from /docs entirely.
They now declare a status-discriminated union. Two things to pin:

1. The OpenAPI document actually carries the models and the status → model map.
2. Declaring a response_model makes FastAPI re-validate and re-serialize every
   response through it — which could silently drop or reshape a field the
   frontend reads. The E2E fixtures (web/e2e/fixtures) are real responses
   recorded before this change, so pushing them back through a response_model
   route must give the same JSON, field for field.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.main import app
from app.schemas import TriageResult, TriageStartResponse

FIXTURES = Path(__file__).resolve().parents[2] / "web" / "e2e" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_triage_models_are_in_the_openapi_document():
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    for model in ("TriageDraft", "TriageResult", "OutOfScopeResult", "ReviewDecision"):
        assert model in schemas, model

    ok = spec["paths"]["/cases/triage"]["post"]["responses"]["200"]
    union = ok["content"]["application/json"]["schema"]
    assert union["discriminator"]["propertyName"] == "status"
    assert set(union["discriminator"]["mapping"]) == {
        "awaiting_review", "approved", "rejected", "out_of_scope",
    }

    approve = spec["paths"]["/cases/{thread_id}/approve"]["post"]["responses"]["200"]
    assert approve["content"]["application/json"]["schema"]["$ref"].endswith("/TriageResult")


@pytest.mark.parametrize(
    "name, response_model",
    [
        ("case_001.draft.json", TriageStartResponse),
        ("case_004.out_of_scope.json", TriageStartResponse),
        ("case_001.approved.json", TriageStartResponse),
        ("case_001.approved.json", TriageResult),
    ],
)
def test_response_model_does_not_change_the_wire_format(name, response_model):
    recorded = _fixture(name)
    model = TypeAdapter(TriageStartResponse).validate_python(recorded)

    probe = FastAPI()
    probe.get("/probe", response_model=response_model)(lambda: model)

    assert TestClient(probe).get("/probe").json() == recorded
