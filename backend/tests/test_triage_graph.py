"""Tests for the triage LangGraph — wiring (4a) + HITL interrupt/resume (4b).

No LLM: fake services only. These pin the *orchestration*, not the per-service
logic (each service has its own suite): the DAG runs every node with the right
upstream state, the human-review gate interrupts and resumes, and the reviewer's
overrides are applied + audited. The pure helpers are tested directly too.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.schemas import (
    AdverseEventMention,
    CaseExtraction,
    CausalityAssessment,
    DrugExpectedness,
    ExpectednessAssessment,
    MeddraCoding,
    Patient,
    ProductMatch,
    ProductMatchResult,
    ReviewDecision,
    SeriousnessAssessment,
    VerdictOverride,
)
from app.services.triage_graph import (
    apply_overrides,
    build_triage_graph,
    compute_escalations,
)


class FakeProductMaster:
    def __init__(self, products):
        self.products = products

    def match(self, text):
        return ProductMatchResult(matched_products=self.products)


class FakeExtraction:
    def __init__(self, events, patient=None):
        self.events = events
        self.patient = patient or Patient()

    def extract(self, text):
        return CaseExtraction(patient=self.patient, adverse_events=self.events)


class FakeMeddra:
    def code(self, terms):
        return [MeddraCoding(term=t, coded_by="該当なし") for t in terms]


class FakeSeriousness:
    """Records what it was handed; returns a fixed verdict for every event."""

    def __init__(self, verdict="非重篤"):
        self.verdict = verdict
        self.seen_codings = None

    def assess(self, text, events, codings):
        self.seen_codings = codings
        return [SeriousnessAssessment(term=ae.term, verdict=self.verdict) for ae in events]


class FakeCausality:
    def __init__(self, verdict="否定できない"):
        self.verdict = verdict
        self.seen_drugs = None

    def assess(self, text, events, suspect_drugs):
        self.seen_drugs = suspect_drugs
        return [CausalityAssessment(term=ae.term, verdict=self.verdict) for ae in events]


class FakeExpectedness:
    def __init__(self, verdict="未知"):
        self.verdict = verdict

    def assess(self, drug_name, label_document, terms):
        return DrugExpectedness(
            drug_name=drug_name,
            label_document=label_document,
            assessments=[ExpectednessAssessment(term=t, verdict=self.verdict) for t in terms],
        )


def _ae(term):
    return AdverseEventMention(term=term, source="reported")


def _build(product_master, extraction, seriousness, causality, expectedness=None, checkpointer=None):
    return build_triage_graph(
        product_master=product_master,
        extraction=extraction,
        meddra=FakeMeddra(),
        seriousness=seriousness,
        causality=causality,
        expectedness=expectedness or FakeExpectedness(),
        checkpointer=checkpointer,
    )


def _drugx():
    return [ProductMatch(name="DrugX", matched_via="name", label_document="drugx_label.md")]


# --- 4a wiring (auto_approve → run to completion, no checkpointer) ---


def test_full_pipeline_populates_every_branch():
    seriousness, causality = FakeSeriousness(), FakeCausality()
    graph = _build(FakeProductMaster(_drugx()), FakeExtraction([_ae("頭痛"), _ae("めまい")]), seriousness, causality)

    final = graph.invoke({"text": "症例テキスト", "document_name": "case.txt", "auto_approve": True})

    assert final["product_match"].is_company_product_present is True
    assert [ae.term for ae in final["extraction"].adverse_events] == ["頭痛", "めまい"]
    assert [m.term for m in final["meddra"]] == ["頭痛", "めまい"]
    assert [s.term for s in final["seriousness"]] == ["頭痛", "めまい"]
    assert [c.term for c in final["causality"]] == ["頭痛", "めまい"]
    assert len(final["expectedness"]) == 1
    assert final["expectedness"][0].drug_name == "DrugX"
    assert [a.term for a in final["expectedness"][0].assessments] == ["頭痛", "めまい"]
    # auto_approve runs the review gate straight through.
    assert final["status"] == "approved"


def test_seriousness_receives_coded_pts_and_causality_receives_suspect_drugs():
    seriousness, causality = FakeSeriousness(), FakeCausality()
    graph = _build(FakeProductMaster(_drugx()), FakeExtraction([_ae("頭痛")]), seriousness, causality)

    graph.invoke({"text": "t", "document_name": "c.txt", "auto_approve": True})

    assert seriousness.seen_codings is not None
    assert [m.term for m in seriousness.seen_codings] == ["頭痛"]
    assert causality.seen_drugs == ["DrugX"]


def test_no_adverse_events_short_circuits_downstream():
    graph = _build(FakeProductMaster(_drugx()), FakeExtraction([]), FakeSeriousness(), FakeCausality())

    final = graph.invoke({"text": "有害事象なし", "document_name": "c.txt", "auto_approve": True})

    assert final["meddra"] == []
    assert final["seriousness"] == []
    assert final["causality"] == []
    assert final["expectedness"] == []


def test_expectedness_skips_products_without_a_label():
    products = [
        ProductMatch(name="DrugX", matched_via="name", label_document="drugx_label.md"),
        ProductMatch(name="OTC", matched_via="alias", label_document=None),
    ]
    graph = _build(FakeProductMaster(products), FakeExtraction([_ae("頭痛")]), FakeSeriousness(), FakeCausality())

    final = graph.invoke({"text": "t", "document_name": "c.txt", "auto_approve": True})

    assert [e.drug_name for e in final["expectedness"]] == ["DrugX"]


# --- 4b HITL: interrupt / resume ---


def _hitl(seriousness=None, causality=None, expectedness=None, events=None):
    return _build(
        FakeProductMaster(_drugx()),
        FakeExtraction(events or [_ae("頭痛")]),
        seriousness or FakeSeriousness(),
        causality or FakeCausality(),
        expectedness=expectedness,
        checkpointer=MemorySaver(),
    )


def test_start_pauses_at_human_review_and_surfaces_escalations():
    graph = _hitl(seriousness=FakeSeriousness("要確認"))
    cfg = {"configurable": {"thread_id": "t1"}}

    out = graph.invoke({"text": "t", "document_name": "c.txt"}, cfg)
    snap = graph.get_state(cfg)

    assert snap.next == ("human_review",)  # paused, not finalized
    assert "status" not in snap.values
    # the interrupt payload carries the escalations for the reviewer.
    payload = out["__interrupt__"][0].value
    assert any(e["axis"] == "seriousness" and e["term"] == "頭痛" for e in payload["escalations"])


def test_resume_approve_applies_override_and_records_audit():
    graph = _hitl(seriousness=FakeSeriousness("要確認"))
    cfg = {"configurable": {"thread_id": "t2"}}
    graph.invoke({"text": "t", "document_name": "c.txt"}, cfg)

    decision = ReviewDecision(
        action="approve",
        reviewer="nabe",
        overrides=[VerdictOverride(axis="seriousness", term="頭痛", new_verdict="重篤", rationale="入院あり")],
    )
    graph.invoke(Command(resume=decision.model_dump()), cfg)
    vals = graph.get_state(cfg).values

    assert vals["status"] == "approved"
    s = vals["seriousness"][0]
    assert s.verdict == "重篤" and s.is_serious is True  # computed field follows the override
    rec = vals["review_outcome"].overrides[0]
    assert (rec.original_verdict, rec.new_verdict, rec.rationale) == ("要確認", "重篤", "入院あり")
    assert vals["review_outcome"].reviewer == "nabe"


def test_resume_records_ime_promotions_in_outcome():
    graph = _hitl(seriousness=FakeSeriousness("要確認"))
    cfg = {"configurable": {"thread_id": "t_ime"}}
    graph.invoke({"text": "t", "document_name": "c.txt"}, cfg)

    # the router resolves promotions into records; simulate that resume payload.
    payload = {
        "action": "approve",
        "reviewer": "nabe",
        "overrides": [],
        "ime_promotion_records": [
            {
                "pt_code": "10002198", "pt_name": "アナフィラキシー反応", "reviewer": "nabe",
                "promoted_at": "2026-08-24T00:00:00", "rationale": "重要", "status": "追加",
            }
        ],
    }
    graph.invoke(Command(resume=payload), cfg)
    vals = graph.get_state(cfg).values

    assert vals["status"] == "approved"
    proms = vals["review_outcome"].ime_promotions
    assert len(proms) == 1
    assert proms[0].pt_code == "10002198" and proms[0].status == "追加"


def test_resume_reject_leaves_verdicts_and_marks_rejected():
    graph = _hitl(seriousness=FakeSeriousness("要確認"))
    cfg = {"configurable": {"thread_id": "t3"}}
    graph.invoke({"text": "t", "document_name": "c.txt"}, cfg)

    decision = ReviewDecision(action="reject", reviewer="nabe", note="対象外")
    graph.invoke(Command(resume=decision.model_dump()), cfg)
    vals = graph.get_state(cfg).values

    assert vals["status"] == "rejected"
    assert vals["seriousness"][0].verdict == "要確認"  # unchanged
    assert vals["review_outcome"].status == "rejected" and vals["review_outcome"].note == "対象外"


# --- pure helpers ---


def test_compute_escalations_flags_only_uncertain_bands():
    seriousness = [SeriousnessAssessment(term="a", verdict="要確認"),
                   SeriousnessAssessment(term="b", verdict="非重篤")]
    causality = [CausalityAssessment(term="a", verdict="評価不能"),
                 CausalityAssessment(term="b", verdict="否定できない")]
    expectedness = [DrugExpectedness(drug_name="DrugX", label_document="l.md",
                                     assessments=[ExpectednessAssessment(term="a", verdict="要確認"),
                                                  ExpectednessAssessment(term="b", verdict="既知")])]

    esc = compute_escalations(seriousness, causality, expectedness)
    flagged = {(e.axis, e.term) for e in esc}

    assert flagged == {("seriousness", "a"), ("causality", "a"), ("expectedness", "a")}


def test_apply_overrides_expectedness_is_nested_and_audited():
    expectedness = [DrugExpectedness(drug_name="DrugX", label_document="l.md",
                                     assessments=[ExpectednessAssessment(term="頭痛", verdict="要確認")])]
    overrides = [{"axis": "expectedness", "term": "頭痛", "drug_name": "DrugX",
                  "new_verdict": "既知", "rationale": "添付文書に記載"}]

    _, _, exp, records = apply_overrides(
        seriousness=[], causality=[], expectedness=expectedness, overrides=overrides
    )

    a = exp[0].assessments[0]
    assert a.verdict == "既知" and a.is_expected is True
    assert records[0].original_verdict == "要確認" and records[0].drug_name == "DrugX"
    # original object is untouched (non-destructive).
    assert expectedness[0].assessments[0].verdict == "要確認"
