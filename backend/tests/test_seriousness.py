"""Unit tests for SeriousnessService (no LLM — fakes only).

Pins the split from ADR 0004: the LLM's criterion hits are turned into a verdict
by a deterministic OR (any 該当 → 重篤; only 疑い → 要確認; none → 非重篤), and the
reporter's value is carried through untouched for the ズレ view. This is the
**fresh** judgment; IME criterion 6 moved to the influence layer (Phase 4e / ADR
0010) and is covered by test_influence.py.
"""

from app.schemas import AdverseEventMention
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


def _svc(chain):
    s = SeriousnessService.__new__(SeriousnessService)
    s.chain = chain
    return s


def _ae(term, reported=None):
    return AdverseEventMention(term=term, source="reported", seriousness_reported=reported)


def test_confirmed_criterion_makes_it_serious():
    chain = FakeChain(
        {
            "徐脈": _SeriousnessJudgment(
                hits=[_CriterionHit(criterion="入院・入院期間の延長", status="該当", evidence_quote="入院した")]
            )
        }
    )
    r = _svc(chain).assess("...", [_ae("徐脈", "非重篤")])[0]

    assert r.verdict == "重篤"
    assert r.is_serious is True
    assert r.reported == "非重篤"  # the ズレ (reporter 非重篤 vs company 重篤) is preserved
    assert r.hits[0].criterion == "入院・入院期間の延長"


def test_only_suspected_is_requires_review():
    chain = FakeChain(
        {"めまい": _SeriousnessJudgment(hits=[_CriterionHit(criterion="生命を脅かす", status="疑い")])}
    )
    r = _svc(chain).assess("...", [_ae("めまい")])[0]

    assert r.verdict == "要確認"
    assert r.is_serious is False
    assert r.hits and r.hits[0].criterion == "生命を脅かす"


def test_no_criteria_is_non_serious():
    chain = FakeChain({"頭痛": _SeriousnessJudgment(hits=[])})
    r = _svc(chain).assess("...", [_ae("頭痛", "非重篤")])[0]

    assert r.verdict == "非重篤"
    assert r.hits == []
