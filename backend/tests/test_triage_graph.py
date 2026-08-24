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
    EventPrecedent,
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
    apply_extraction_edits,
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
    def __init__(self, codes=None):
        self.codes = codes or {}

    def code(self, terms):
        return [
            MeddraCoding(
                term=t, pt_code=self.codes.get(t), pt_name_ja=t,
                coded_by="完全一致" if self.codes.get(t) else "該当なし",
            )
            for t in terms
        ]


class FakeSeriousness:
    """Fresh judgment: returns a fixed verdict for every event (no past data)."""

    def __init__(self, verdict="非重篤"):
        self.verdict = verdict

    def assess(self, text, events):
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


class FakePrecedent:
    def __init__(self, result=None):
        self.result = result or []

    def summarize(self, drugs, meddra, seriousness, causality, expectedness):
        return self.result


class FakeInfluence:
    """Pass-through influence layer (no past-data effects) for wiring tests."""

    def apply(self, mode, meddra, seriousness, causality, expectedness, precedent):
        return seriousness, causality, expectedness, [], mode


def _ae(term):
    return AdverseEventMention(term=term, source="reported")


def _build(product_master, extraction, seriousness, causality, expectedness=None,
           precedent=None, influence=None, meddra=None, checkpointer=None):
    return build_triage_graph(
        product_master=product_master,
        extraction=extraction,
        meddra=meddra or FakeMeddra(),
        seriousness=seriousness,
        causality=causality,
        expectedness=expectedness or FakeExpectedness(),
        precedent=precedent or FakePrecedent(),
        influence=influence or FakeInfluence(),
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


def test_causality_receives_suspect_drugs():
    causality = FakeCausality()
    graph = _build(FakeProductMaster(_drugx()), FakeExtraction([_ae("頭痛")]), FakeSeriousness(), causality)

    graph.invoke({"text": "t", "document_name": "c.txt", "auto_approve": True})

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


def _hitl(seriousness=None, causality=None, expectedness=None, precedent=None,
          influence=None, events=None):
    return _build(
        FakeProductMaster(_drugx()),
        FakeExtraction(events or [_ae("頭痛")]),
        seriousness or FakeSeriousness(),
        causality or FakeCausality(),
        expectedness=expectedness,
        precedent=precedent,
        influence=influence,
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


def test_influence_mode_applied_vs_advisory_changes_the_verdict():
    from app.services.influence import InfluenceService

    class FakeIme2:
        def contains(self, code):
            return code == "10002198"

        def note(self, code):
            return "例示" if code == "10002198" else None

    meddra = FakeMeddra({"アナフィラキシー反応": "10002198"})
    events = [_ae("アナフィラキシー反応")]

    applied = _build(
        FakeProductMaster(_drugx()), FakeExtraction(events), FakeSeriousness("非重篤"),
        FakeCausality(), meddra=meddra, influence=InfluenceService(FakeIme2()),
    ).invoke({"text": "t", "document_name": "c", "auto_approve": True, "influence_mode": "applied"})
    assert applied["seriousness"][0].verdict == "重篤"  # IME criterion 6 applied
    assert any(it.source == "IME" and it.applied for it in applied["influence"])

    advisory = _build(
        FakeProductMaster(_drugx()), FakeExtraction(events), FakeSeriousness("非重篤"),
        FakeCausality(), meddra=meddra, influence=InfluenceService(FakeIme2()),
    ).invoke({"text": "t", "document_name": "c", "auto_approve": True, "influence_mode": "advisory"})
    assert advisory["seriousness"][0].verdict == "非重篤"  # left fresh
    assert any(it.source == "IME" and not it.applied for it in advisory["influence"])


def test_precedent_conflict_surfaces_as_escalation():
    ep = EventPrecedent(
        term="頭痛", pt_code="10019211", n_cases=2,
        seriousness={"重篤": 2}, conflicts=["seriousness"], case_ids=["A", "B"],
    )
    graph = _hitl(seriousness=FakeSeriousness("非重篤"), precedent=FakePrecedent([ep]))
    cfg = {"configurable": {"thread_id": "t_prec"}}

    out = graph.invoke({"text": "t", "document_name": "c.txt"}, cfg)

    payload = out["__interrupt__"][0].value
    assert any(
        e["axis"] == "seriousness" and "過去症例と不一致" in e["reason"]
        for e in payload["escalations"]
    )
    snap = graph.get_state(cfg)
    assert snap.values["precedent"][0].conflicts == ["seriousness"]


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


def _ext(terms):
    return CaseExtraction(
        patient=Patient(),
        adverse_events=[AdverseEventMention(term=t, source="reported") for t in terms],
    )


def test_extraction_edit_remove_drops_from_all_lists():
    ext = _ext(["頭痛", "そう痒症"])
    med = [MeddraCoding(term="頭痛", coded_by="該当なし"), MeddraCoding(term="そう痒症", coded_by="該当なし")]
    ser = [SeriousnessAssessment(term="頭痛", verdict="非重篤"), SeriousnessAssessment(term="そう痒症", verdict="非重篤")]
    cau = [CausalityAssessment(term="頭痛", verdict="否定できない"), CausalityAssessment(term="そう痒症", verdict="否定できない")]

    e, m, s, c, x, p, i, rec = apply_extraction_edits(
        extraction=ext, meddra=med, seriousness=ser, causality=cau, expectedness=[],
        precedent=[], influence=[], removed=["そう痒症"], added=[], recoded=[],
    )
    assert [a.term for a in e.adverse_events] == ["頭痛"]
    assert [z.term for z in m] == ["頭痛"] and [z.term for z in s] == ["頭痛"] and [z.term for z in c] == ["頭痛"]
    assert rec[0].kind == "removed" and rec[0].term == "そう痒症"


def test_extraction_edit_recode_replaces_pt_manually():
    ext = _ext(["肝機能異常"])
    med = [MeddraCoding(term="肝機能異常", pt_code="10019837", pt_name_ja="肝機能異常", coded_by="完全一致")]
    _, m, *_rest, rec = apply_extraction_edits(
        extraction=ext, meddra=med, seriousness=[], causality=[], expectedness=[],
        precedent=[], influence=[], removed=[], added=[],
        recoded=[{"term": "肝機能異常", "pt_code": "10072268", "pt_name": "薬物性肝障害"}],
    )
    assert m[0].pt_code == "10072268" and m[0].pt_name_ja == "薬物性肝障害" and m[0].coded_by == "手動"
    assert any(r.kind == "recoded" for r in rec)


def test_extraction_edit_add_appends_with_manual_verdicts():
    ext = _ext(["頭痛"])
    e, m, s, c, *_rest, rec = apply_extraction_edits(
        extraction=ext, meddra=[MeddraCoding(term="頭痛", coded_by="該当なし")],
        seriousness=[SeriousnessAssessment(term="頭痛", verdict="非重篤")],
        causality=[CausalityAssessment(term="頭痛", verdict="否定できない")],
        expectedness=[], precedent=[], influence=[], removed=[], recoded=[],
        added=[{"term": "発疹", "pt_code": "10037844", "pt_name": "発疹",
                "seriousness": "要確認", "causality": "否定できない"}],
    )
    assert [a.term for a in e.adverse_events] == ["頭痛", "発疹"]
    assert m[-1].term == "発疹" and m[-1].coded_by == "手動" and m[-1].pt_code == "10037844"
    assert s[-1].term == "発疹" and s[-1].verdict == "要確認"
    assert c[-1].term == "発疹"
    assert any(r.kind == "added" and r.term == "発疹" for r in rec)


def test_resume_with_extraction_remove_edit_reaches_final():
    graph = _hitl(events=[_ae("頭痛"), _ae("そう痒症")])
    cfg = {"configurable": {"thread_id": "t_edit"}}
    graph.invoke({"text": "t", "document_name": "c.txt"}, cfg)

    decision = ReviewDecision(action="approve", reviewer="nabe", removed_terms=["そう痒症"])
    graph.invoke(Command(resume=decision.model_dump()), cfg)
    vals = graph.get_state(cfg).values

    assert [a.term for a in vals["extraction"].adverse_events] == ["頭痛"]
    assert [s.term for s in vals["seriousness"]] == ["頭痛"]
    assert vals["review_outcome"].extraction_edits[0].kind == "removed"


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
