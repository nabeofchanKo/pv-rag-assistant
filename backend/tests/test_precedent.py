"""Tests for PrecedentService (Phase 4d) — structured per-(drug, PT) precedent.

No LLM. Covers: indexing seed records, per-event summary + counts, the
consistency conflict flag (current draft vs precedent majority), event-level
dedupe across drugs, and save → in-memory index refresh (a just-approved case
becomes precedent immediately).
"""

import json

from app.schemas import (
    CausalityAssessment,
    MeddraCoding,
    PastCaseEvent,
    PastCaseRecord,
    SeriousnessAssessment,
)
from app.services.precedent import PrecedentService


def _seed(tmp_path):
    seed = tmp_path / "seed"
    runtime = tmp_path / "runtime"
    seed.mkdir()
    rec = PastCaseRecord(
        case_id="ICSR-PAST-1", date="2025-01-01", drugs=["DrugZ"], reviewer="r",
        events=[
            PastCaseEvent(term="鼻出血", pt_code="10015090", pt_name="鼻出血",
                          seriousness="重篤", causality="否定できない", expectedness={"DrugZ": "既知"}),
        ],
    )
    (seed / "p1.json").write_text(rec.model_dump_json(), encoding="utf-8")
    rec2 = rec.model_copy(update={"case_id": "ICSR-PAST-2"})
    (seed / "p2.json").write_text(rec2.model_dump_json(), encoding="utf-8")
    return PrecedentService(str(seed), str(runtime))


def _meddra(term, code):
    return MeddraCoding(term=term, pt_code=code, pt_name_ja=term, coded_by="完全一致")


def test_summary_counts_and_no_conflict_when_agreeing(tmp_path):
    svc = _seed(tmp_path)
    ep = svc.summarize(
        ["DrugZ"],
        [_meddra("鼻出血", "10015090")],
        [SeriousnessAssessment(term="鼻出血", verdict="重篤")],
        [CausalityAssessment(term="鼻出血", verdict="否定できない")],
        [],
    )[0]

    assert ep.n_cases == 2
    assert ep.seriousness == {"重篤": 2}
    assert sorted(ep.case_ids) == ["ICSR-PAST-1", "ICSR-PAST-2"]
    assert ep.conflicts == []  # current 重篤 agrees with precedent majority


def test_conflict_flagged_when_current_differs(tmp_path):
    svc = _seed(tmp_path)
    ep = svc.summarize(
        ["DrugZ"],
        [_meddra("鼻出血", "10015090")],
        [SeriousnessAssessment(term="鼻出血", verdict="非重篤")],  # differs from past 重篤
        [CausalityAssessment(term="鼻出血", verdict="否定できない")],
        [],
    )[0]

    assert "seriousness" in ep.conflicts
    assert ep.seriousness == {"重篤": 2}


def test_no_pt_or_no_match_yields_empty_precedent(tmp_path):
    svc = _seed(tmp_path)
    # PT not in the store
    ep = svc.summarize(
        ["DrugZ"], [_meddra("頭痛", "10019211")],
        [SeriousnessAssessment(term="頭痛", verdict="非重篤")],
        [CausalityAssessment(term="頭痛", verdict="否定できない")], [],
    )[0]
    assert ep.n_cases == 0 and ep.conflicts == [] and ep.seriousness == {}


def test_save_makes_case_available_immediately(tmp_path):
    svc = _seed(tmp_path)
    new = PastCaseRecord(
        case_id="ICSR-NEW", drugs=["DrugX"],
        events=[PastCaseEvent(term="回転性めまい", pt_code="10047340", seriousness="重篤",
                              causality="否定できない", expectedness={"DrugX": "要確認"})],
    )
    svc.save(new)

    ep = svc.summarize(
        ["DrugX"], [_meddra("回転性めまい", "10047340")],
        [SeriousnessAssessment(term="回転性めまい", verdict="非重篤")],
        [CausalityAssessment(term="回転性めまい", verdict="否定できない")], [],
    )[0]
    assert ep.n_cases == 1 and "seriousness" in ep.conflicts
    # persisted to the runtime dir
    saved = json.loads((tmp_path / "runtime" / "ICSR-NEW.json").read_text(encoding="utf-8"))
    assert saved["case_id"] == "ICSR-NEW"
