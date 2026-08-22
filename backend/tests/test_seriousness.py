"""Unit tests for SeriousnessService (no LLM — fakes only).

Pins the split from ADR 0004: the LLM's criterion hits are turned into a verdict by
a deterministic OR (any 該当 → 重篤; only 疑い → 要確認; none → 非重篤), criterion 6
also fires deterministically from the IME list, and the reporter's value is carried
through untouched for the ズレ view.
"""

from app.schemas import AdverseEventMention, MeddraCoding
from app.services.seriousness import (
    SeriousnessService,
    _CriterionHit,
    _SeriousnessJudgment,
)


class FakeChain:
    def __init__(self, by_term):
        self.by_term = by_term

    def invoke(self, inputs):
        return self.by_term[inputs["term"]]


class FakeIme:
    def __init__(self, codes):
        self.codes = set(codes)

    def contains(self, code):
        return bool(code) and code in self.codes


def _svc(chain, ime):
    s = SeriousnessService.__new__(SeriousnessService)
    s.ime = ime
    s.chain = chain
    return s


def _ae(term, reported=None):
    return AdverseEventMention(term=term, source="reported", seriousness_reported=reported)


def _coding(term, pt_code):
    return MeddraCoding(term=term, pt_code=pt_code, pt_name_ja=term, coded_by="完全一致")


def test_confirmed_criterion_makes_it_serious():
    chain = FakeChain(
        {
            "徐脈": _SeriousnessJudgment(
                hits=[_CriterionHit(criterion="入院・入院期間の延長", status="該当", evidence_quote="入院した")]
            )
        }
    )
    svc = _svc(chain, FakeIme([]))

    r = svc.assess("...", [_ae("徐脈", "非重篤")], [_coding("徐脈", "10006093")])[0]

    assert r.verdict == "重篤"
    assert r.is_serious is True
    assert r.reported == "非重篤"  # the ズレ (reporter 非重篤 vs company 重篤) is preserved
    assert r.hits[0].criterion == "入院・入院期間の延長"


def test_only_suspected_is_requires_review():
    chain = FakeChain(
        {"めまい": _SeriousnessJudgment(hits=[_CriterionHit(criterion="生命を脅かす", status="疑い")])}
    )
    svc = _svc(chain, FakeIme([]))

    r = svc.assess("...", [_ae("めまい")], [_coding("めまい", "10013573")])[0]

    assert r.verdict == "要確認"
    assert r.is_serious is False
    assert r.hits and r.hits[0].criterion == "生命を脅かす"


def test_no_criteria_is_non_serious():
    chain = FakeChain({"頭痛": _SeriousnessJudgment(hits=[])})
    svc = _svc(chain, FakeIme([]))

    r = svc.assess("...", [_ae("頭痛", "非重篤")], [_coding("頭痛", "10019211")])[0]

    assert r.verdict == "非重篤"
    assert r.hits == []


def test_ime_pt_flags_criterion6_deterministically():
    # LLM finds nothing, but the coded PT is on the IME list -> 重篤 via criterion 6.
    chain = FakeChain({"アナフィラキシー反応": _SeriousnessJudgment(hits=[])})
    svc = _svc(chain, FakeIme(["10002198"]))

    r = svc.assess("...", [_ae("アナフィラキシー反応")], [_coding("アナフィラキシー反応", "10002198")])[0]

    assert r.verdict == "重篤"
    assert any(h.source == "IME" and h.criterion == "医学的に重要" for h in r.hits)


def test_ime_does_not_duplicate_medically_important():
    chain = FakeChain(
        {"x": _SeriousnessJudgment(hits=[_CriterionHit(criterion="医学的に重要", status="該当")])}
    )
    svc = _svc(chain, FakeIme(["111"]))

    r = svc.assess("...", [_ae("x")], [_coding("x", "111")])[0]

    assert [h.criterion for h in r.hits].count("医学的に重要") == 1
