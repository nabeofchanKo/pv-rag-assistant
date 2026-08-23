"""Tests for the influence layer (Phase 4e) — applied vs advisory past-data.

Applied: IME → criterion 6 = 重篤 (deterministic, with provenance); precedent →
safe-side nudge to 要確認 only (never a downgrade); causality kept in scope.
Advisory: verdicts unchanged, the same signals recorded as notes. No LLM.
"""

from app.schemas import (
    CausalityAssessment,
    EventPrecedent,
    MeddraCoding,
    SeriousnessAssessment,
)
from app.services.influence import InfluenceService


class FakeIme:
    def __init__(self, notes=None):
        self.notes = notes or {}

    def contains(self, code):
        return bool(code) and code in self.notes

    def note(self, code):
        return self.notes.get(code)


def _m(term, code):
    return MeddraCoding(term=term, pt_code=code, pt_name_ja=term, coded_by="完全一致")


def _s(term, v):
    return SeriousnessAssessment(term=term, verdict=v)


def _c(term, v):
    return CausalityAssessment(term=term, verdict=v)


def test_applied_ime_fires_criterion6_to_serious_with_provenance():
    inf = InfluenceService(FakeIme({"10047290": "HITL昇格 田中PV担当 2026-08-24"}))
    ser, cau, exp, items, mode = inf.apply(
        "applied", [_m("心室細動", "10047290")], [_s("心室細動", "非重篤")],
        [_c("心室細動", "否定できない")], [], [],
    )
    assert mode == "applied"
    assert ser[0].verdict == "重篤"
    hit = next(h for h in ser[0].hits if h.source == "IME")
    assert "HITL昇格 田中PV担当" in hit.evidence_quote
    assert any(it.source == "IME" and it.applied and it.to_verdict == "重篤" for it in items)


def test_applied_precedent_nudges_up_but_caps_at_review():
    ep = EventPrecedent(term="鼻出血", pt_code="10015090", n_cases=2,
                        seriousness={"重篤": 2}, case_ids=["A", "B"])
    inf = InfluenceService(FakeIme())
    ser, _, _, items, _ = inf.apply(
        "applied", [_m("鼻出血", "10015090")], [_s("鼻出血", "非重篤")],
        [_c("鼻出血", "否定できない")], [], [ep],
    )
    assert ser[0].verdict == "要確認"  # nudged up, NOT auto-重篤
    assert any(it.source == "precedent" and it.to_verdict == "要確認" for it in items)


def test_applied_precedent_never_downgrades():
    ep = EventPrecedent(term="頭痛", pt_code="10019211", n_cases=3,
                        seriousness={"非重篤": 3}, case_ids=["A"])
    inf = InfluenceService(FakeIme())
    ser, _, _, items, _ = inf.apply(
        "applied", [_m("頭痛", "10019211")], [_s("頭痛", "重篤")],
        [_c("頭痛", "否定できない")], [], [ep],
    )
    assert ser[0].verdict == "重篤"  # not pulled down by past 非重篤
    assert not any(it.axis == "seriousness" and it.applied for it in items)


def test_applied_causality_kept_in_scope():
    ep = EventPrecedent(term="めまい", pt_code="10013573", n_cases=2,
                        causality={"否定できない": 2}, case_ids=["A", "B"])
    inf = InfluenceService(FakeIme())
    _, cau, _, items, _ = inf.apply(
        "applied", [_m("めまい", "10013573")], [_s("めまい", "非重篤")],
        [_c("めまい", "否定できる")], [], [ep],
    )
    assert cau[0].verdict == "否定できない"
    assert any(it.axis == "causality" and it.to_verdict == "否定できない" for it in items)


def test_advisory_leaves_verdicts_and_only_notes():
    ep = EventPrecedent(term="鼻出血", pt_code="10015090", n_cases=2,
                        seriousness={"重篤": 2}, causality={"否定できない": 2}, case_ids=["A", "B"])
    inf = InfluenceService(FakeIme({"10015090": "HITL昇格"}))
    ser, cau, exp, items, mode = inf.apply(
        "advisory", [_m("鼻出血", "10015090")], [_s("鼻出血", "非重篤")],
        [_c("鼻出血", "否定できない")], [], [ep],
    )
    assert mode == "advisory"
    assert ser[0].verdict == "非重篤" and cau[0].verdict == "否定できない"  # unchanged
    assert items and all(not it.applied for it in items)
    assert any(it.source == "IME" for it in items)
    assert any(it.source == "precedent" for it in items)
