"""Unit tests for CausalityService (no LLM — fakes only).

Pins the conservative deterministic rule (ADR 0005): 否定できない by default; 否定できる
only for onset-before-administration or a clearly-incompatible post-discontinuation
onset; 評価不能 only when the temporal relation is unknown.
"""

import pytest

from app.schemas import AdverseEventMention
from app.services.causality import CausalityService, _Judgment, _verdict


@pytest.mark.parametrize(
    "onset_relation,clearly_excludable,expected",
    [
        ("投与開始前", False, "否定できる"),
        ("投与開始前", True, "否定できる"),
        ("投与中", False, "否定できない"),
        ("投与中止後", False, "否定できない"),  # residual/delayed effect not excluded
        ("投与中止後", True, "否定できる"),  # clearly incompatible
        ("不明", False, "評価不能"),
    ],
)
def test_verdict_rule(onset_relation, clearly_excludable, expected):
    assert _verdict(onset_relation, clearly_excludable) == expected


class FakeChain:
    def __init__(self, by_term):
        self.by_term = by_term

    def invoke(self, inputs):
        return self.by_term[inputs["term"]]


def _svc(chain):
    s = CausalityService.__new__(CausalityService)
    s.chain = chain
    return s


def _ae(term, onset=None):
    return AdverseEventMention(term=term, source="reported", onset_date=onset)


def test_default_is_not_excludable_and_preserves_term():
    chain = FakeChain(
        {"頭痛": _Judgment(onset_relation="投与中", evidence_quote="投与3日後に発現")}
    )
    svc = _svc(chain)

    c = svc.assess("...", [_ae("頭痛", "2025-11-04")], ["DrugX"])[0]

    assert c.term == "頭痛"
    assert c.verdict == "否定できない"
    assert c.is_excludable is False
    assert c.onset_relation == "投与中"


def test_onset_before_administration_is_excludable():
    chain = FakeChain(
        {"頭痛": _Judgment(onset_relation="投与開始前", evidence_quote="投与前から頭痛あり")}
    )
    c = _svc(chain).assess("...", [_ae("頭痛")], ["DrugX"])[0]

    assert c.verdict == "否定できる"
    assert c.is_excludable is True


def test_post_discontinuation_with_lingering_effect_stays_not_excludable():
    chain = FakeChain(
        {"錯乱状態": _Judgment(onset_relation="投与中止後", clearly_excludable=False)}
    )
    c = _svc(chain).assess("...", [_ae("錯乱状態")], ["DrugZ"])[0]

    assert c.verdict == "否定できない"
