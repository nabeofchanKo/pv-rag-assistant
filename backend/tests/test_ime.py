"""Tests for IME promotion (Phase 4c) — the HITL-feeds-accuracy loop.

`ImeReference.promote` grows the important-medical-events list (in-memory + CSV),
and the payoff test proves the point of Phase 4c: after a reviewer promotes a PT,
the *next* seriousness assessment of an event coded to that PT fires E2A
criterion 6 automatically. No LLM (fakes only).
"""

import csv

from app.schemas import AdverseEventMention, MeddraCoding
from app.services.ime import ImeReference
from app.services.seriousness import SeriousnessService, _SeriousnessJudgment


def _write_csv(path, rows=()):
    body = "pt_code,pt_name_ja,note\n" + "".join(f"{c},{n},{note}\n" for c, n, note in rows)
    path.write_text(body, encoding="utf-8")


def _rows(path):
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


def test_promote_updates_memory_and_persists(tmp_path):
    csvp = tmp_path / "ime.csv"
    _write_csv(csvp, [("10008190", "心停止", "例示")])
    ime = ImeReference(str(csvp))
    assert ime.contains("10008190")
    assert not ime.contains("10002198")

    added = ime.promote("10002198", "アナフィラキシー反応", "HITL昇格 nabe 2026-08-24")
    assert added is True
    assert ime.contains("10002198")  # visible in-memory immediately

    # persisted: a fresh reference over the same file sees it (survives restart)
    assert ImeReference(str(csvp)).contains("10002198")
    codes = [r["pt_code"] for r in _rows(csvp)]
    assert codes == ["10008190", "10002198"]


def test_promote_is_idempotent_no_duplicate_row(tmp_path):
    csvp = tmp_path / "ime.csv"
    _write_csv(csvp, [("111", "x", "例示")])
    ime = ImeReference(str(csvp))

    assert ime.promote("111", "x", "重複") is False  # already present
    assert [r["pt_code"] for r in _rows(csvp)].count("111") == 1


def test_promote_blank_code_is_noop(tmp_path):
    csvp = tmp_path / "ime.csv"
    _write_csv(csvp)
    ime = ImeReference(str(csvp))
    assert ime.promote("  ", "x") is False


class _NoHitChain:
    """Stands in for the LLM: never finds a criterion, so only IME can flag it."""

    def invoke(self, inputs):
        return _SeriousnessJudgment(hits=[])


def _seriousness(ime):
    svc = SeriousnessService.__new__(SeriousnessService)
    svc.ime = ime
    svc.chain = _NoHitChain()
    return svc


def test_promotion_feeds_the_next_seriousness_assessment(tmp_path):
    csvp = tmp_path / "ime.csv"
    _write_csv(csvp)  # empty list to start
    ime = ImeReference(str(csvp))
    svc = _seriousness(ime)

    ae = AdverseEventMention(term="心室細動", source="reported")
    coding = MeddraCoding(term="心室細動", pt_code="10047290", pt_name_ja="心室細動", coded_by="完全一致")

    before = svc.assess("...", [ae], [coding])[0]
    assert before.verdict == "非重篤"  # LLM finds nothing, PT not yet on IME

    ime.promote("10047290", "心室細動", "HITL昇格 nabe 2026-08-24")

    after = svc.assess("...", [ae], [coding])[0]
    assert after.verdict == "重篤"  # same input, now serious via criterion 6
    assert any(h.source == "IME" and h.criterion == "医学的に重要" for h in after.hits)
