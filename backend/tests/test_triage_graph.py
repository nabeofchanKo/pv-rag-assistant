"""Wiring tests for the Phase 4a LangGraph triage graph (no LLM — fakes only).

These do not re-test the per-service logic (each service has its own suite);
they pin the *orchestration*: the DAG runs every node, feeds each node the
right upstream state (coded PTs into seriousness, suspect drugs into causality,
labelled products into expectedness), and the empty-case short-circuits hold —
i.e. behaviour parity with the previous imperative router.
"""

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
    SeriousnessAssessment,
)
from app.services.triage_graph import build_triage_graph


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
    """Records what it was handed so we can assert the coded PTs reached it."""

    def __init__(self):
        self.seen_codings = None

    def assess(self, text, events, codings):
        self.seen_codings = codings
        return [SeriousnessAssessment(term=ae.term, verdict="非重篤") for ae in events]


class FakeCausality:
    def __init__(self):
        self.seen_drugs = None

    def assess(self, text, events, suspect_drugs):
        self.seen_drugs = suspect_drugs
        return [CausalityAssessment(term=ae.term, verdict="否定できない") for ae in events]


class FakeExpectedness:
    def assess(self, drug_name, label_document, terms):
        return DrugExpectedness(
            drug_name=drug_name,
            label_document=label_document,
            assessments=[ExpectednessAssessment(term=t, verdict="未知") for t in terms],
        )


def _ae(term):
    return AdverseEventMention(term=term, source="reported")


def _build(product_master, extraction, seriousness, causality):
    return build_triage_graph(
        product_master=product_master,
        extraction=extraction,
        meddra=FakeMeddra(),
        seriousness=seriousness,
        causality=causality,
        expectedness=FakeExpectedness(),
    )


def test_full_pipeline_populates_every_branch():
    products = [ProductMatch(name="DrugX", matched_via="name", label_document="drugx_label.md")]
    seriousness = FakeSeriousness()
    causality = FakeCausality()
    graph = _build(
        FakeProductMaster(products),
        FakeExtraction([_ae("頭痛"), _ae("めまい")]),
        seriousness,
        causality,
    )

    final = graph.invoke({"text": "症例テキスト", "document_name": "case.txt"})

    assert final["product_match"].is_company_product_present is True
    assert [ae.term for ae in final["extraction"].adverse_events] == ["頭痛", "めまい"]
    assert [m.term for m in final["meddra"]] == ["頭痛", "めまい"]
    assert [s.term for s in final["seriousness"]] == ["頭痛", "めまい"]
    assert [c.term for c in final["causality"]] == ["頭痛", "めまい"]
    # expectedness: one entry per labelled product, covering every term.
    assert len(final["expectedness"]) == 1
    assert final["expectedness"][0].drug_name == "DrugX"
    assert [a.term for a in final["expectedness"][0].assessments] == ["頭痛", "めまい"]


def test_seriousness_receives_coded_pts_and_causality_receives_suspect_drugs():
    products = [ProductMatch(name="DrugX", matched_via="name", label_document="drugx_label.md")]
    seriousness = FakeSeriousness()
    causality = FakeCausality()
    graph = _build(
        FakeProductMaster(products), FakeExtraction([_ae("頭痛")]), seriousness, causality
    )

    graph.invoke({"text": "t", "document_name": "c.txt"})

    # meddra output flowed into seriousness (criterion 6 / IME needs the PT).
    assert seriousness.seen_codings is not None
    assert [m.term for m in seriousness.seen_codings] == ["頭痛"]
    # product match flowed into causality as the suspect-drug anchor.
    assert causality.seen_drugs == ["DrugX"]


def test_no_adverse_events_short_circuits_downstream():
    products = [ProductMatch(name="DrugX", matched_via="name", label_document="drugx_label.md")]
    graph = _build(
        FakeProductMaster(products), FakeExtraction([]), FakeSeriousness(), FakeCausality()
    )

    final = graph.invoke({"text": "有害事象なし", "document_name": "c.txt"})

    assert final["meddra"] == []
    assert final["seriousness"] == []
    assert final["causality"] == []
    # no terms → nothing to assess against the label either.
    assert final["expectedness"] == []


def test_expectedness_skips_products_without_a_label():
    products = [
        ProductMatch(name="DrugX", matched_via="name", label_document="drugx_label.md"),
        ProductMatch(name="OTC", matched_via="alias", label_document=None),
    ]
    graph = _build(
        FakeProductMaster(products), FakeExtraction([_ae("頭痛")]), FakeSeriousness(), FakeCausality()
    )

    final = graph.invoke({"text": "t", "document_name": "c.txt"})

    # only the labelled product yields an expectedness block.
    assert [e.drug_name for e in final["expectedness"]] == ["DrugX"]
