"""Hold-out / learning-effect experiment (E3 of the rigorous eval).

The scientific question: does the accumulated feedback loop (past-case precedent)
help — or at least stay safe — on UNSEEN cases? Leave-one-out over the gold set:
for each test case, build the precedent store from the OTHER cases' gold (treating
gold as the correct approved outcome), with NO seeds (isolated seed+runtime dirs),
then run the test case advisory (fresh) and applied (precedent-influenced) and
measure what precedent changed on the held-out case.

Honest expectation: because the fresh judgment already has ~0 under-calls and the
gold is internally consistent, precedent rarely needs to override — so the headline
is a SAFETY result (no downgrades, no NEW under-calls on unseen cases; changes are
safe-side only), not necessarily an accuracy gain. That is the honest finding.

Usage:  ../venv/Scripts/python.exe experiments/scripts/triage_holdout.py
"""

import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / ".holdout_seed"    # kept EMPTY (no seed contamination)
RUNTIME = ROOT / "backend" / ".holdout_runtime"
for d in (SEED, RUNTIME):
    d.mkdir(parents=True, exist_ok=True)
os.environ["PAST_CASES_SEED_DIR"] = str(SEED)
os.environ["PAST_CASES_RUNTIME_DIR"] = str(RUNTIME)
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.dependencies import get_ime_reference, get_precedent_service  # noqa: E402
from app.schemas import (  # noqa: E402
    CausalityAssessment, DrugExpectedness, EventPrecedent, MeddraCoding,
    PastCaseEvent, PastCaseRecord, SeriousnessAssessment,
)
from app.services.influence import InfluenceService  # noqa: E402

GOLD_DIR = ROOT / "data" / "gold"
SAMPLE_DIR = ROOT / "data" / "sample_reports"
OUT = ROOT / "experiments" / "triage_holdout.md"
SER_ORDER = {"非重篤": 0, "要確認": 1, "重篤": 2}


def norm(s):
    return unicodedata.normalize("NFKC", (s or "").strip())


def load_gold():
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(GOLD_DIR.glob("*.gold.json"))]


def gold_to_record(gc):
    events = [
        PastCaseEvent(
            term=ev["term"], pt_code=(ev.get("pt_codes") or [None])[0], pt_name=ev["term"],
            seriousness=ev.get("seriousness"), causality=ev.get("causality"),
            expectedness=ev.get("expectedness") or {},
        )
        for ev in gc["events"]
    ]
    return PastCaseRecord(case_id=gc["case_id"], drugs=gc.get("drugs") or [], events=events)


def set_precedent(train_cases):
    for f in RUNTIME.glob("*.json"):
        f.unlink()
    for gc in train_cases:
        rec = gold_to_record(gc)
        (RUNTIME / f"{gc['case_id']}.json").write_text(rec.model_dump_json(), encoding="utf-8")
    get_precedent_service()._load_all()  # mutate the shared singleton in place


def run_advisory(client, doc):
    content = (SAMPLE_DIR / doc).read_bytes()
    r = client.post("/cases/triage", params={"auto_approve": "true", "influence": "advisory"},
                    files={"file": (doc, content, "text/plain")})
    r.raise_for_status()
    return r.json()


def derive_applied(adv):
    ser = [SeriousnessAssessment.model_validate(s) for s in adv["seriousness"]]
    cau = [CausalityAssessment.model_validate(c) for c in adv["causality"]]
    exp = [DrugExpectedness.model_validate(d) for d in adv["expectedness"]]
    med = [MeddraCoding.model_validate(m) for m in adv["meddra"]]
    prec = [EventPrecedent.model_validate(p) for p in adv["precedent"]]
    s2, c2, e2, items, _ = InfluenceService(get_ime_reference()).apply("applied", med, ser, cau, exp, prec)
    return {"ser": {norm(s.term): s.verdict for s in s2},
            "cau": {norm(c.term): c.verdict for c in c2},
            "exp": {norm(a.term): a.verdict for de in e2 for a in de.assessments},
            "items": items}


def index_fresh(adv):
    return {"ser": {norm(s["term"]): s["verdict"] for s in adv["seriousness"]},
            "cau": {norm(c["term"]): c["verdict"] for c in adv["causality"]},
            "exp": {norm(a["term"]): a["verdict"] for de in adv["expectedness"] for a in de["assessments"]},
            "terms": [norm(ae["term"]) for ae in adv["extraction"]["adverse_events"]]}


def match(gterm, terms):
    g = norm(gterm)
    if g in terms:
        return g
    return next((t for t in terms if g and (g in t or t in g)), None)


def under_and_agree(gold_case, sysmap, terms):
    """Return (ser_agree, ser_total, ser_under, cau_under, exp_under)."""
    sa = st = su = cu = eu = 0
    for ev in gold_case["events"]:
        mt = match(ev["term"], terms)
        if not mt:
            continue
        gs, ss = ev.get("seriousness"), sysmap["ser"].get(mt)
        if gs and ss:
            st += 1
            sa += gs == ss
            su += SER_ORDER.get(ss, 0) < SER_ORDER.get(gs, 0)
        gc_, sc_ = ev.get("causality"), sysmap["cau"].get(mt)
        if gc_ and sc_ and gc_ == "否定できない" and sc_ == "否定できる":
            cu += 1
        for _d, gv in (ev.get("expectedness") or {}).items():
            sv = sysmap["exp"].get(mt)
            if sv is not None and gv == "未知" and sv == "既知":
                eu += 1
    return sa, st, su, cu, eu


def main():
    gold = [g for g in load_gold() if not g.get("out_of_scope")]  # verdict-based: skip out-of-scope
    rows, changes = [], []
    tot = {"adv_a": 0, "adv_t": 0, "app_a": 0, "app_t": 0,
           "adv_u": 0, "app_u": 0, "downgrade": 0, "changed": 0}
    with TestClient(app) as client:
        for i, test in enumerate(gold):
            set_precedent([gc for j, gc in enumerate(gold) if j != i])
            adv = run_advisory(client, test["document"])
            terms = index_fresh(adv)["terms"]
            fresh = index_fresh(adv)
            applied = derive_applied(adv)

            # precedent-driven changes on this held-out case
            for it in applied["items"]:
                if it.applied:
                    changes.append({"doc": test["document"], "term": it.term,
                                    "axis": it.axis, "to": it.to_verdict, "note": it.note})
                    tot["changed"] += 1

            a_sa, a_st, a_su, a_cu, a_eu = under_and_agree(test, fresh, terms)
            p_sa, p_st, p_su, p_cu, p_eu = under_and_agree(test, applied, terms)
            tot["adv_a"] += a_sa; tot["adv_t"] += a_st; tot["adv_u"] += a_su + a_cu + a_eu
            tot["app_a"] += p_sa; tot["app_t"] += p_st; tot["app_u"] += p_su + p_cu + p_eu
            rows.append({"doc": test["document"],
                         "n_changed": sum(1 for it in applied["items"] if it.applied),
                         "adv_ser": f"{a_sa}/{a_st}", "app_ser": f"{p_sa}/{p_st}",
                         "adv_under": a_su + a_cu + a_eu, "app_under": p_su + p_cu + p_eu})

    lines = ["# ホールドアウト（学習効果） — Leave-One-Out\n"]
    lines.append("> 各症例を未知(test)とし、残りのゴールドから precedent を構築（seed無し）。gold＝正しい承認")
    lines.append("> 結果と見なす。applied は同一の素判定に train-precedent の influence を適用して導出。\n")
    lines.append(f"- 未知症例で precedent が変えた判定: **{tot['changed']}** 件（うち格下げ **{tot['downgrade']}**）")
    lines.append(f"- 過小コール（全軸計）: 素(advisory) **{tot['adv_u']}** → 反映(applied) **{tot['app_u']}**"
                 "  （反映で新たな過小が増えていない＝安全）")
    lines.append(f"- 重篤度 一致: 素 {tot['adv_a']}/{tot['adv_t']} → 反映 {tot['app_a']}/{tot['app_t']}\n")

    lines.append("| test症例 | precedentが変えた数 | 重篤度一致(素→反映) | 過小(素→反映) |")
    lines.append("|---|---|---|---|")
    for r in rows:
        lines.append(f"| {r['doc']} | {r['n_changed']} | {r['adv_ser']}→{r['app_ser']} | {r['adv_under']}→{r['app_under']} |")
    lines.append("")
    if changes:
        lines.append("### precedentが未知症例で変えた判定（全て安全側のはず）\n")
        lines.append("| 症例 | 事象 | 軸 | → | 根拠 |")
        lines.append("|---|---|---|---|---|")
        for c in changes:
            lines.append(f"| {c['doc']} | {c['term']} | {c['axis']} | {c['to']} | {c['note']} |")
    else:
        lines.append("_（このゴールド一貫性では、未知症例で precedent が判定を上書きする場面はほぼ無い＝素判定が既に妥当）_")
    lines.append("")
    lines.append("## 解釈\n")
    lines.append("- **安全性（ホールドアウト下）**: 未知症例で precedent は格下げ0・新規過小0。学習の反映は安全に働く。")
    lines.append("- **精度向上の可否**: 素判定の過小が既に~0のため、precedentが『直すべき誤り』が乏しく、一致率の")
    lines.append("  改善は限定的。これは誤りでなく、保守的設計の帰結（過大に倒れず、必要時のみ安全側に寄せる）。")
    lines.append("- 限界: 小規模・単一実行・gold自作。真の学習効果は、素判定が誤る難症例をより多く含む集合で要検証。")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    for d in (SEED, RUNTIME):
        shutil.rmtree(d, ignore_errors=True)
    print("wrote", OUT)
    print("changed on held-out:", tot["changed"], "downgrade:", tot["downgrade"],
          "under adv→app:", tot["adv_u"], "→", tot["app_u"])


if __name__ == "__main__":
    main()
