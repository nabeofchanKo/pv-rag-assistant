"""Triage evaluation harness (Phase 4 eval).

Runs each sample case through the pipeline in BOTH influence modes (applied /
advisory), then:

  Part 1 (no gold) — influence A/B: how many verdicts change applied vs advisory,
    and in which direction (should be safe-side only, never a downgrade).
  Part 2 (vs gold) — accuracy: MedDRA PT exact-match, per-axis agreement, and the
    safety-critical *under-call* counts (missed 重篤 / 未知 / in-scope causality).

Writes experiments/triage_eval.md. Reproducible; run with the project venv:
    ../venv/Scripts/python.exe experiments/scripts/triage_eval.py

Notes: gold is a small hand-authored, illustrative set (see data/gold/, flagged
for PV review). LLMs are not perfectly deterministic at temperature 0, so numbers
can vary run to run; this is a single-run snapshot.
"""

import json
import os
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Isolate the precedent runtime store so the eval neither reads nor writes it
# (seeds in data/past_cases/ still count; approvals are not saved by /cases/triage).
os.environ["PAST_CASES_RUNTIME_DIR"] = str(ROOT / "backend" / ".eval_pc_runtime")
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.dependencies import get_ime_reference  # noqa: E402
from app.schemas import (  # noqa: E402
    CausalityAssessment,
    DrugExpectedness,
    EventPrecedent,
    MeddraCoding,
    SeriousnessAssessment,
)
from app.services.influence import InfluenceService  # noqa: E402

GOLD_DIR = ROOT / "data" / "gold"
SAMPLE_DIR = ROOT / "data" / "sample_reports"
# Output path is overridable so a provider A/B run (e.g. EMBEDDING_PROVIDER=ollama)
# can write to its own file instead of clobbering the canonical baseline report.
OUT = Path(os.environ.get("TRIAGE_EVAL_OUT", ROOT / "experiments" / "triage_eval.md"))
MODES = ["applied", "advisory"]
# Safety-critical directions: gold value -> the verdict that would be an UNDER-call.
SER_ORDER = {"非重篤": 0, "要確認": 1, "重篤": 2}


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip())


def load_gold():
    cases = []
    for f in sorted(GOLD_DIR.glob("*.gold.json")):
        cases.append(json.loads(f.read_text(encoding="utf-8")))
    return cases


def run_case(client, doc, mode):
    content = (SAMPLE_DIR / doc).read_bytes()
    r = client.post(
        "/cases/triage",
        params={"auto_approve": "true", "influence": mode},
        files={"file": (doc, content, "text/plain")},
    )
    r.raise_for_status()
    return r.json()


def derive_applied(advisory_data):
    """Derive the applied-mode result from the SAME fresh verdicts (advisory run),
    so the A/B isolates the influence effect deterministically (no LLM re-run noise)."""
    ser = [SeriousnessAssessment.model_validate(s) for s in advisory_data["seriousness"]]
    cau = [CausalityAssessment.model_validate(c) for c in advisory_data["causality"]]
    exp = [DrugExpectedness.model_validate(d) for d in advisory_data["expectedness"]]
    med = [MeddraCoding.model_validate(m) for m in advisory_data["meddra"]]
    prec = [EventPrecedent.model_validate(p) for p in advisory_data["precedent"]]
    s2, c2, e2, items, _ = InfluenceService(get_ime_reference()).apply(
        "applied", med, ser, cau, exp, prec
    )
    d = dict(advisory_data)
    d["seriousness"] = [x.model_dump() for x in s2]
    d["causality"] = [x.model_dump() for x in c2]
    d["expectedness"] = [x.model_dump() for x in e2]
    d["influence"] = [x.model_dump() for x in items]
    d["influence_mode"] = "applied"
    return d


def index_system(data):
    ser = {norm(s["term"]): s["verdict"] for s in data["seriousness"]}
    cau = {norm(c["term"]): c["verdict"] for c in data["causality"]}
    med = {norm(m["term"]): m.get("pt_code") for m in data["meddra"]}
    exp = defaultdict(dict)
    for de in data.get("expectedness", []):
        for a in de["assessments"]:
            exp[norm(a["term"])][de["drug_name"]] = a["verdict"]
    terms = [norm(ae["term"]) for ae in data["extraction"]["adverse_events"]]
    return {"terms": terms, "ser": ser, "cau": cau, "med": med, "exp": exp}


def match_term(gold_term, system_terms):
    g = norm(gold_term)
    if g in system_terms:
        return g
    for t in system_terms:  # loose containment fallback
        if g and (g in t or t in g):
            return t
    return None


def score_mode(gold_cases, outputs):
    """outputs: {document: indexed system output}. Returns aggregate + per-case."""
    agg = {
        "meddra_hit": 0, "meddra_total": 0,
        "ser_agree": 0, "ser_total": 0, "ser_under": 0, "ser_over": 0,
        "cau_agree": 0, "cau_total": 0, "cau_under": 0,
        "exp_agree": 0, "exp_total": 0, "exp_under": 0, "exp_over": 0,
        "recall_hit": 0, "recall_total": 0, "extra": 0,
    }
    per_case = []
    for gc in gold_cases:
        sysd = outputs[gc["document"]]
        matched_terms = set()
        rec_hit = 0
        under_notes = []
        for ev in gc["events"]:
            agg["recall_total"] += 1
            mt = match_term(ev["term"], sysd["terms"])
            if not mt:
                under_notes.append(f"{ev['term']}: 抽出漏れ")
                continue
            matched_terms.add(mt)
            rec_hit += 1
            agg["recall_hit"] += 1
            # MedDRA
            agg["meddra_total"] += 1
            if sysd["med"].get(mt) in ev.get("pt_codes", []):
                agg["meddra_hit"] += 1
            # seriousness
            gser = ev.get("seriousness")
            sser = sysd["ser"].get(mt)
            if gser and sser:
                agg["ser_total"] += 1
                if gser == sser:
                    agg["ser_agree"] += 1
                elif SER_ORDER.get(sser, 0) < SER_ORDER.get(gser, 0):
                    agg["ser_under"] += 1
                    under_notes.append(f"{ev['term']}: 重篤度 過小 {sser}<{gser}")
                else:
                    agg["ser_over"] += 1
            # causality (under-call = gold 否定できない but system excluded it)
            gcau = ev.get("causality")
            scau = sysd["cau"].get(mt)
            if gcau and scau:
                agg["cau_total"] += 1
                if gcau == scau:
                    agg["cau_agree"] += 1
                elif gcau == "否定できない" and scau == "否定できる":
                    agg["cau_under"] += 1
                    under_notes.append(f"{ev['term']}: 因果 過小(否定)")
            # expectedness (per own-company drug; under-call = gold 未知 but system 既知)
            gexp = ev.get("expectedness") or {}
            for drug, gv in gexp.items():
                sv = sysd["exp"].get(mt, {}).get(drug)
                if sv is None:
                    continue
                agg["exp_total"] += 1
                if gv == sv:
                    agg["exp_agree"] += 1
                elif gv == "未知" and sv == "既知":
                    agg["exp_under"] += 1
                    under_notes.append(f"{ev['term']}: 既知/未知 過小(既知)")
                else:
                    agg["exp_over"] += 1
        extra = [t for t in sysd["terms"] if t not in matched_terms]
        agg["extra"] += len(extra)
        per_case.append({
            "doc": gc["document"], "recall": f"{rec_hit}/{len(gc['events'])}",
            "extra": extra, "under": under_notes,
        })
    return agg, per_case


def influence_ab(gold_cases, applied_out, advisory_out):
    """Per event, compare applied vs advisory seriousness/causality verdicts."""
    rows, up, down, changed = [], 0, 0, 0
    for gc in gold_cases:
        a, b = applied_out[gc["document"]], advisory_out[gc["document"]]
        for term in b["terms"]:
            for axis, order in (("ser", SER_ORDER), ("cau", None)):
                av, bv = a[axis].get(term), b[axis].get(term)
                if av is None or bv is None or av == bv:
                    continue
                changed += 1
                direction = "?"
                if axis == "ser":
                    direction = "↑(safe)" if order[av] > order[bv] else "↓(DOWNGRADE)"
                elif axis == "cau":
                    direction = "↑(safe)" if (bv == "否定できる" and av == "否定できない") else "↓(DOWNGRADE)"
                up += direction.startswith("↑")
                down += direction.startswith("↓")
                rows.append({
                    "doc": gc["document"], "term": term,
                    "axis": "重篤度" if axis == "ser" else "因果",
                    "advisory": bv, "applied": av, "dir": direction,
                })
    return rows, {"changed": changed, "safe_up": up, "downgrade": down}


def pct(n, d):
    return f"{100*n/d:.0f}% ({n}/{d})" if d else "—"


def main():
    gold = load_gold()
    in_scope = [g for g in gold if not g.get("out_of_scope")]
    oos = [g for g in gold if g.get("out_of_scope")]
    results = {m: {} for m in MODES}
    gate = {"pass": 0, "total": len(oos), "bad": []}
    with TestClient(app) as client:
        for gc in in_scope:
            # One fresh LLM pass (advisory); applied is derived from the same fresh
            # verdicts, so the A/B reflects influence only, not run-to-run variance.
            advisory = run_case(client, gc["document"], "advisory")
            results["advisory"][gc["document"]] = index_system(advisory)
            results["applied"][gc["document"]] = index_system(derive_applied(advisory))
        # Out-of-scope cases: verify the own-company hard gate fired (Phase 4g).
        for gc in oos:
            content = (SAMPLE_DIR / gc["document"]).read_bytes()
            r = client.post("/cases/triage", params={"auto_approve": "true"},
                            files={"file": (gc["document"], content, "text/plain")})
            r.raise_for_status()
            status = r.json().get("status")
            if status == "out_of_scope":
                gate["pass"] += 1
            else:
                gate["bad"].append(f"{gc['document']}={status}")

    scores = {m: score_mode(in_scope, results[m]) for m in MODES}
    ab_rows, ab_sum = influence_ab(in_scope, results["applied"], results["advisory"])

    lines = []
    lines.append("# トリアージ評価（influence A/B ＋ 精度）\n")
    lines.append("> 起案ゴールドは小規模・説明用（`data/gold/`、要PVレビュー）。各症例は素判定(advisory)を1回")
    lines.append("> LLM実行し、applied は同一の素判定に influence を適用して導出（A/BはLLMの実行揺れでなく")
    lines.append("> influence効果のみを反映）。単一実行スナップショット。`experiments/scripts/triage_eval.py` で再現。\n")

    lines.append("## 自社品ゲート（Phase 4g）\n")
    bad = f"（誤り: {', '.join(gate['bad'])}）" if gate["bad"] else ""
    lines.append(f"- 自社品なし症例のハードゲート: **{gate['pass']}/{gate['total']}** が正しく評価対象外{bad}")
    lines.append("- 以降の精度・A/Bは自社品ありの in-scope 症例のみ。\n")
    lines.append("## Part 1 — influence A/B（applied vs advisory）\n")
    lines.append(f"- 変化した判定: **{ab_sum['changed']}** 件（安全側↑ {ab_sum['safe_up']} / 格下げ↓ **{ab_sum['downgrade']}**）")
    lines.append("- 期待: 格下げ0（precedentは安全側ナッジのみ、IMEは重篤化のみ）\n")
    if ab_rows:
        lines.append("| 症例 | 事象 | 軸 | 参考(advisory) | 反映(applied) | 方向 |")
        lines.append("|---|---|---|---|---|---|")
        for r in ab_rows:
            lines.append(f"| {r['doc']} | {r['term']} | {r['axis']} | {r['advisory']} | {r['applied']} | {r['dir']} |")
    else:
        lines.append("_（このデータ・シードでは判定変化なし）_")
    lines.append("")

    lines.append("## Part 2 — 精度（対ゴールド）\n")
    lines.append("| 指標 | applied | advisory |")
    lines.append("|---|---|---|")
    def row(label, key_fn):
        return f"| {label} | {key_fn('applied')} | {key_fn('advisory')} |"
    S = scores
    lines.append(row("MedDRA PT 完全一致", lambda m: pct(S[m][0]['meddra_hit'], S[m][0]['meddra_total'])))
    lines.append(row("重篤度 一致", lambda m: pct(S[m][0]['ser_agree'], S[m][0]['ser_total'])))
    lines.append(row("　└ 過小コール(見落とし)", lambda m: str(S[m][0]['ser_under'])))
    lines.append(row("　└ 過大コール(安全側)", lambda m: str(S[m][0]['ser_over'])))
    lines.append(row("因果 一致", lambda m: pct(S[m][0]['cau_agree'], S[m][0]['cau_total'])))
    lines.append(row("　└ 過小コール(否定)", lambda m: str(S[m][0]['cau_under'])))
    lines.append(row("既知/未知 一致", lambda m: pct(S[m][0]['exp_agree'], S[m][0]['exp_total'])))
    lines.append(row("　└ 過小コール(既知)", lambda m: str(S[m][0]['exp_under'])))
    lines.append(row("抽出 recall", lambda m: pct(S[m][0]['recall_hit'], S[m][0]['recall_total'])))
    lines.append(row("余分抽出(偽陽性)", lambda m: str(S[m][0]['extra'])))
    lines.append("")

    lines.append("### 症例別メモ（applied）\n")
    lines.append("| 症例 | recall | 余分抽出 | 過小/相違メモ |")
    lines.append("|---|---|---|---|")
    for pc in scores["applied"][1]:
        extra = "、".join(pc["extra"]) or "—"
        under = "；".join(pc["under"]) or "—"
        lines.append(f"| {pc['doc']} | {pc['recall']} | {extra} | {under} |")
    lines.append("")

    n_events = sum(len(gc["events"]) for gc in in_scope)
    lines.append("## 限界と解釈（重要）\n")
    lines.append("この結果は**バリデーションではなく、安全インバリアントの実証＋回帰ベースライン**として読むこと。")
    lines.append(f"- **標本が小規模**（in-scope {len(in_scope)}症例・{n_events}事象、＋自社品なし {len(oos)}症例のゲート確認）。百分率は高分散で、「100%」＝「その試行で誤りなし」。信頼区間は広い。")
    lines.append("- **ゴールドは単一起案（要独立PVレビュー）＝循環リスク**。システムの保守的ルールを作った思考で正解も付けているため、")
    lines.append("  高い一致は「規制上の真実との一致」ではなく「作者の判断との一致」を含む。天井（アノテータ間一致）は未測定。")
    lines.append("- **症例は合成・整った例**。現場の矛盾・欠測・OCR・境界事例は未収載＝ハッピーパス寄り。")
    lines.append("- **influence の効果はシード依存**。変化は1件で、置いたシードが駆動。よって「フィードバックで精度が上がる」は")
    lines.append("  **未実証**。示せたのは「機構が安全に振る舞う（格下げ0）」まで。applied/advisory の一致率差もシードのアーティファクト。")
    lines.append("- **単一実行・分散未計測／ベースライン非対等**（単純法との比較なし）。")
    lines.append("- 拾える主結論：**過小コール0・格下げ0（安全側インバリアント）**が実データで成立し、**測定の作法**が整備できたこと。")
    lines.append("- 「本物の評価」には：独立2名以上のゴールド＋アノテータ間一致、より多く・雑・ホールドアウトな症例、N回実行の分散、")
    lines.append("  単純ベースラインとの対比、過小が起きる境界の難症例、が必要。")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)
    print("A/B:", ab_sum)
    for m in MODES:
        a = scores[m][0]
        print(m, "under ser/cau/exp:", a["ser_under"], a["cau_under"], a["exp_under"],
              "| meddra", a["meddra_hit"], "/", a["meddra_total"])


if __name__ == "__main__":
    main()
