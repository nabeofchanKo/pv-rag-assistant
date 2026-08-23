"""Tests for IME promotion mechanics (Phase 4c).

`ImeReference.promote` grows the important-medical-events list (in-memory + CSV,
idempotent, with provenance in the note). The payoff — a promoted PT firing E2A
criterion 6 on the next assessment — now lives in the influence layer and is
covered by test_influence.py (Phase 4e). No LLM (fakes only).
"""

import csv

from app.services.ime import ImeReference


def _write_csv(path, rows=()):
    body = "pt_code,pt_name_ja,note\n" + "".join(f"{c},{n},{note}\n" for c, n, note in rows)
    path.write_text(body, encoding="utf-8")


def _rows(path):
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


def test_promote_updates_memory_and_persists(tmp_path):
    csvp = tmp_path / "ime.csv"
    _write_csv(csvp, [("DEMO-0037", "心停止", "例示")])
    ime = ImeReference(str(csvp))
    assert ime.contains("DEMO-0037")
    assert not ime.contains("DEMO-0049")

    added = ime.promote("DEMO-0049", "アナフィラキシー反応", "HITL昇格 nabe 2026-08-24")
    assert added is True
    assert ime.contains("DEMO-0049")  # visible in-memory immediately

    # persisted: a fresh reference over the same file sees it (survives restart)
    assert ImeReference(str(csvp)).contains("DEMO-0049")
    codes = [r["pt_code"] for r in _rows(csvp)]
    assert codes == ["DEMO-0037", "DEMO-0049"]


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


def test_note_returns_provenance(tmp_path):
    csvp = tmp_path / "ime.csv"
    _write_csv(csvp, [("DEMO-0049", "アナフィラキシー反応", "例示（EMA IME 相当）")])
    ime = ImeReference(str(csvp))
    assert ime.note("DEMO-0049") == "例示（EMA IME 相当）"
    assert ime.note("00000000") is None

    ime.promote("DEMO-9001", "心室細動", "HITL昇格 田中PV担当 2026-08-24")
    assert ime.note("DEMO-9001") == "HITL昇格 田中PV担当 2026-08-24"
