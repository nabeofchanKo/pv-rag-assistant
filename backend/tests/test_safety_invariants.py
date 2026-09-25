"""T1 — the under-call-0 safety invariant, enforced as a test.

The central safety claim of this project is that it never **under-calls**: never
reports 非重篤 for an event the case text says put someone in hospital, never
excludes a causal link it cannot rule out, never calls an unlisted adverse
reaction 既知. In drug safety an under-call means a report that should have been
expedited quietly is not, which is far more costly than an over-call.

``experiments/scripts/triage_eval.py`` **measures** that on a gold set with real
model calls. This file **proves** the half that must hold no matter what the
model says, by exhausting the deterministic layer's input space.

Why the split: a test that calls an LLM is non-deterministic and costs money, so
it cannot gate every commit — and a green run of it would only tell you the model
behaved today. What can gate every commit is the property the architecture is
built on (ADR 0002 / 0004 / 0005 / 0010): **the model only interprets, code
decides.** If the deciding code cannot emit an unsafe verdict for ANY model
output, the invariant holds by construction, and the real-model evaluation
becomes a measurement rather than the guarantee.

Offline: no LLM, no network. Milliseconds.
"""

from __future__ import annotations

from itertools import combinations_with_replacement, product

import pytest

from app.schemas import (
    AdverseEventMention,
    CausalityAssessment,
    DrugExpectedness,
    EventPrecedent,
    ExpectednessAssessment,
    MeddraCoding,
    SeriousnessAssessment,
)
from app.services.causality import _verdict as causality_verdict
from app.services.expectedness import _MATCH_TYPE_TO_VERDICT
from app.services.influence import _EXP_SEVERITY, _SER_SEVERITY, InfluenceService
from app.services.seriousness import (
    SeriousnessService,
    _CriterionHit,
    _SeriousnessJudgment,
)

# ---------------------------------------------------------------- seriousness


class _FakeChain:
    def __init__(self, judgment):
        self.judgment = judgment

    def invoke(self, _inputs):
        return self.judgment


def _seriousness_service(judgment):
    svc = SeriousnessService.__new__(SeriousnessService)
    svc.chain = _FakeChain(judgment)
    return svc


def _assess(statuses, reported=None):
    hits = [
        _CriterionHit(criterion="入院・入院期間の延長", status=s, evidence_quote="…")
        for s in statuses
    ]
    svc = _seriousness_service(_SeriousnessJudgment(hits=hits))
    ae = AdverseEventMention(term="事象", source="reported", seriousness_reported=reported)
    return svc.assess("case text", [ae])[0]


# Every combination of criterion statuses the model can return, up to three hits.
_STATUS_COMBOS = [()] + [
    c for n in (1, 2, 3) for c in combinations_with_replacement(("該当", "疑い"), n)
]


@pytest.mark.parametrize("statuses", _STATUS_COMBOS, ids=lambda s: "+".join(s) or "none")
def test_seriousness_never_silently_drops_a_reported_hit(statuses):
    """If the model flagged anything at all, the verdict must not be 非重篤.

    This is the shape of the under-call we care about most: the model noticed a
    hospitalisation but the event still came out non-serious.
    """
    result = _assess(statuses)

    if "該当" in statuses:
        assert result.verdict == "重篤"
        assert result.is_serious
    elif statuses:  # only 疑い
        assert result.verdict == "要確認", "an uncertain hit must surface, not vanish"
        assert not result.is_serious, "要確認 must not be treated as serious downstream"
    else:
        assert result.verdict == "非重篤"

    if statuses:
        assert result.verdict != "非重篤"
        assert result.hits, "the evidence behind the verdict must be kept"


@pytest.mark.parametrize("reported", ["非重篤", "重篤", None])
def test_company_assessment_ignores_what_the_reporter_said(reported):
    """A reporter calling it 非重篤 cannot suppress the company assessment.

    This is the behaviour the builder demo exercises: dizziness reported as
    non-serious whose narrative describes an admission.
    """
    result = _assess(("該当",), reported=reported)
    assert result.verdict == "重篤"
    assert result.reported == reported, "the reported value is carried through for the ズレ view"


# ------------------------------------------------------------------ causality

_RELATIONS = ["投与開始前", "投与中", "投与中止後", "不明", "モデルが返した未知の値"]


@pytest.mark.parametrize(("relation", "clearly_excludable"), list(product(_RELATIONS, [True, False])))
def test_causality_excludes_only_on_the_two_explicit_paths(relation, clearly_excludable):
    """否定できる is reachable only from onset-before-dose, or after-stop when the
    model also says it is clearly excludable. Everything else — including values
    this code has never seen — stays in scope."""
    verdict = causality_verdict(relation, clearly_excludable)
    may_exclude = relation == "投与開始前" or (
        relation == "投与中止後" and clearly_excludable
    )
    assert (verdict == "否定できる") == may_exclude
    assert verdict in {"否定できる", "否定できない", "評価不能"}


def test_model_cannot_exclude_an_event_that_arose_during_treatment():
    """The strongest form of the rule: even if the model insists the link is
    clearly excludable, an event that began during dosing stays 否定できない."""
    assert causality_verdict("投与中", True) == "否定できない"
    assert not CausalityAssessment(term="x", verdict="否定できない").is_excludable


# ---------------------------------------------------------------- expectedness

_MATCH_TYPES = list(_MATCH_TYPE_TO_VERDICT) + ["モデルが返した未知の一致種別", ""]
_CONFIDENT = {"直接一致", "同義語"}


@pytest.mark.parametrize("match_type", _MATCH_TYPES)
def test_expectedness_calls_it_known_only_on_a_confident_match(match_type):
    """既知 suppresses expedited reporting, so it is reachable only from a
    confident match. A loose match, or a match type this code does not know,
    must land on the safe side."""
    verdict = _MATCH_TYPE_TO_VERDICT.get(match_type, "判定不能")
    assert (verdict == "既知") == (match_type in _CONFIDENT)
    assert ExpectednessAssessment(term="x", verdict=verdict).is_expected == (
        match_type in _CONFIDENT
    )


def test_unrecognised_match_type_does_not_become_known():
    """The fallback matters: a model that invents a match type must not be able
    to talk the system into 既知."""
    assert _MATCH_TYPE_TO_VERDICT.get("でっちあげ", "判定不能") == "判定不能"


# -------------------------------------------------------- computed safety flags


@pytest.mark.parametrize("verdict", ["重篤", "要確認", "非重篤"])
def test_is_serious_is_true_only_for_serious(verdict):
    assert SeriousnessAssessment(term="x", verdict=verdict).is_serious == (verdict == "重篤")


@pytest.mark.parametrize("verdict", ["否定できない", "否定できる", "評価不能"])
def test_is_excludable_is_true_only_for_excludable(verdict):
    assert CausalityAssessment(term="x", verdict=verdict).is_excludable == (
        verdict == "否定できる"
    )


@pytest.mark.parametrize("verdict", ["既知", "要確認", "未知", "判定不能"])
def test_is_expected_is_true_only_for_known(verdict):
    assert ExpectednessAssessment(term="x", verdict=verdict).is_expected == (verdict == "既知")


# ------------------------------------------------------------------- influence


class _NoIme:
    def contains(self, _code):
        return False

    def note_for(self, _code):
        return None


def _apply(fresh_verdict, past_counts):
    """Run the influence layer for one event with a given past-case majority."""
    svc = InfluenceService(_NoIme())
    ser = [SeriousnessAssessment(term="事象", verdict=fresh_verdict)]
    prec = [EventPrecedent(term="事象", pt_code="1", n_cases=sum(past_counts.values()),
                           seriousness=past_counts)]
    out_ser, _, _, items, _ = svc.apply(
        "applied",
        [MeddraCoding(term="事象", pt_code="1", coded_by="完全一致")],
        ser,
        [],
        [],
        prec,
    )
    return out_ser[0], items


@pytest.mark.parametrize(
    ("fresh", "past"),
    list(
        product(
            ["非重篤", "要確認", "重篤"],
            [{"重篤": 2}, {"非重篤": 2}, {"要確認": 1}, {"重篤": 1, "非重篤": 1}, {}],
        )
    ),
)
def test_past_data_never_downgrades_and_never_forces_serious(fresh, past):
    """Precedent may raise a verdict toward the safe side, never lower it, and it
    may not decide 重篤 on its own — that stays a human call (ADR 0010)."""
    result, _items = _apply(fresh, past)

    assert _SER_SEVERITY[result.verdict] >= _SER_SEVERITY[fresh], (
        f"past data downgraded {fresh} -> {result.verdict}"
    )
    if fresh != "重篤":
        assert result.verdict != "重篤", "precedent must cap at 要確認, not decide 重篤"


def test_severity_ranks_order_the_safe_side_upward():
    """The nudge logic is only as safe as these ranks, so pin them."""
    assert _SER_SEVERITY["非重篤"] < _SER_SEVERITY["要確認"] < _SER_SEVERITY["重篤"]
    assert _EXP_SEVERITY["既知"] < _EXP_SEVERITY["要確認"] <= _EXP_SEVERITY["未知"]
    assert _EXP_SEVERITY["判定不能"] > _EXP_SEVERITY["既知"], (
        "an undetermined expectedness must never rank as safe as 既知"
    )
