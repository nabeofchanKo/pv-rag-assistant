"""Contract test: the hand-written TypeScript types must match the Pydantic models.

ADR 0013 chose to mirror ``backend/app/schemas.py`` by hand in
``web/src/lib/types.ts`` rather than generate it — the contract is small and
stable, and codegen would have bought little at this size. The cost of that
choice is silent drift: rename a field in Python and the frontend keeps reading
``undefined`` with nothing failing until someone opens the page. This test is
the mitigation named in that ADR.

It compares the **Pydantic models** rather than the OpenAPI document on purpose.
The triage routes declare ``response_model=None`` because they return a union
(``TriageDraft | TriageResult | OutOfScopeResult``), so those response schemas
never appear in OpenAPI at all — a contract test built on the spec would silently
cover none of the models that matter most.

Runs offline: no server, no network, no LLM calls.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import schemas
from app.services.triage_graph import ALLOWED_VERDICTS

WEB = Path(__file__).resolve().parents[2] / "web" / "src" / "lib"
TYPES_TS = WEB / "types.ts"
LABELS_TS = WEB / "labels.ts"

# Pydantic model -> TypeScript interface. TriageResponse is called TriageContent
# on the frontend because there it is the shared base of draft and result.
CONTRACT: dict[str, str] = {
    "SourceInfo": "SourceInfo",
    "QueryResponse": "QueryResponse",
    "UploadResponse": "UploadResponse",
    "Patient": "Patient",
    "AdverseEventMention": "AdverseEventMention",
    "CaseExtraction": "CaseExtraction",
    "ProductMatch": "ProductMatch",
    "ProductMatchResult": "ProductMatchResult",
    "MeddraTerm": "MeddraTerm",
    "MeddraCoding": "MeddraCoding",
    "SeriousnessHit": "SeriousnessHit",
    "SeriousnessAssessment": "SeriousnessAssessment",
    "CausalityAssessment": "CausalityAssessment",
    "ExpectednessAssessment": "ExpectednessAssessment",
    "DrugExpectedness": "DrugExpectedness",
    "EventPrecedent": "EventPrecedent",
    "InfluenceItem": "InfluenceItem",
    "Escalation": "Escalation",
    "TriageResponse": "TriageContent",
    "TriageDraft": "TriageDraft",
    "TriageResult": "TriageResult",
    "OutOfScopeResult": "OutOfScopeResult",
    "VerdictOverride": "VerdictOverride",
    "ImePromotion": "ImePromotion",
    "AddedEvent": "AddedEvent",
    "RecodedEvent": "RecodedEvent",
    "ReviewDecision": "ReviewDecision",
    "OverrideRecord": "OverrideRecord",
    "ImePromotionRecord": "ImePromotionRecord",
    "ExtractionEditRecord": "ExtractionEditRecord",
    "ReviewOutcome": "ReviewOutcome",
}

_INTERFACE_RE = re.compile(
    r"export\s+interface\s+(?P<name>\w+)(?:\s+extends\s+(?P<parent>\w+))?\s*\{"
)
_FIELD_RE = re.compile(r"^\s*(?P<field>\w+)\??\s*:")


def _parse_interfaces(source: str) -> dict[str, tuple[set[str], str | None]]:
    """Map interface name -> (own field names, parent name).

    Deliberately small: it understands the one declaration style this file uses
    (one field per line, no inline object literals). It tracks brace depth so a
    nested type could not silently swallow the rest of the file, and the
    completeness test below fails loudly if an expected interface goes missing.
    """
    out: dict[str, tuple[set[str], str | None]] = {}
    for m in _INTERFACE_RE.finditer(source):
        depth = 1
        fields: set[str] = set()
        for line in source[m.end():].splitlines():
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
            if depth == 1:  # only the interface's own top level
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                f = _FIELD_RE.match(line)
                if f:
                    fields.add(f.group("field"))
        out[m.group("name")] = (fields, m.group("parent"))
    return out


def _ts_fields(name: str, parsed: dict[str, tuple[set[str], str | None]]) -> set[str]:
    """All fields of a TS interface, following `extends`."""
    seen: set[str] = set()
    current: str | None = name
    while current:
        entry = parsed.get(current)
        if entry is None:
            break
        fields, parent = entry
        seen |= fields
        current = parent
    return seen


def _py_fields(model_name: str) -> set[str]:
    """Serialized field names of a Pydantic model, including computed fields.

    computed_field properties (is_serious, is_expected, is_excludable,
    is_company_product_present) ARE serialized, so the frontend relies on them
    and they belong in the contract.
    """
    model = getattr(schemas, model_name)
    return set(model.model_fields) | set(model.model_computed_fields)


@pytest.fixture(scope="module")
def parsed_types() -> dict[str, tuple[set[str], str | None]]:
    assert TYPES_TS.exists(), f"missing {TYPES_TS}"
    return _parse_interfaces(TYPES_TS.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("py_name", "ts_name"), sorted(CONTRACT.items()))
def test_model_fields_match_typescript(py_name, ts_name, parsed_types):
    """Every Pydantic field has a TS counterpart and vice versa."""
    assert ts_name in parsed_types, (
        f"TypeScript interface '{ts_name}' not found in types.ts — "
        f"it mirrors the Pydantic model '{py_name}'."
    )

    py = _py_fields(py_name)
    ts = _ts_fields(ts_name, parsed_types)

    missing_in_ts = py - ts
    extra_in_ts = ts - py
    assert not missing_in_ts, (
        f"{py_name} -> {ts_name}: fields exist in Python but not TypeScript "
        f"(the frontend will read undefined): {sorted(missing_in_ts)}"
    )
    assert not extra_in_ts, (
        f"{py_name} -> {ts_name}: fields exist in TypeScript but not Python "
        f"(the frontend expects data the API never sends): {sorted(extra_in_ts)}"
    )


def test_contract_covers_every_response_model():
    """A new response model must be added to the contract, not just to schemas.py."""
    from pydantic import BaseModel

    declared = {
        name
        for name, obj in vars(schemas).items()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
    }
    # Internal/domain models the frontend never sees.
    internal = {
        "PageContent",
        "ProcessedDocument",
        "Chunk",
        "RAGResponse",
        "QueryRequest",
        "AdverseEventCore",
        "PastCaseEvent",
        "PastCaseRecord",
    }
    uncovered = declared - set(CONTRACT) - internal
    assert not uncovered, (
        "these Pydantic models are neither in the frontend contract nor marked "
        f"internal — decide which and update this test: {sorted(uncovered)}"
    )


def test_verdict_options_match_backend():
    """The UI's selectable verdicts must equal what the API will accept.

    The review form builds its dropdowns from these lists; a value outside
    ALLOWED_VERDICTS is rejected 422 server-side, so drift here shows up as a
    reviewer being unable to record a verdict the backend supports.
    """
    labels = LABELS_TS.read_text(encoding="utf-8")

    def options(const: str) -> set[str]:
        m = re.search(rf"export const {const}\s*=\s*\[(?P<body>.*?)\]", labels, re.S)
        assert m, f"{const} not found in labels.ts"
        return set(re.findall(r'"([^"]+)"', m.group("body")))

    for axis, const in (
        ("seriousness", "SER_OPTIONS"),
        ("causality", "CAU_OPTIONS"),
        ("expectedness", "EXP_OPTIONS"),
    ):
        assert options(const) == ALLOWED_VERDICTS[axis], (
            f"{const} does not match ALLOWED_VERDICTS['{axis}']: "
            f"frontend={sorted(options(const))} backend={sorted(ALLOWED_VERDICTS[axis])}"
        )
