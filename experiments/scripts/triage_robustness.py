"""Robustness / run-to-run variance (E1 of the rigorous eval).

Runs each sample case K times through the FRESH pipeline (advisory mode — the
influence layer is deterministic, so all variance is LLM-driven) and reports:

  * Extraction stability — which events appear in ALL K runs vs only some (flaky).
  * Verdict stability — for stable events, is each axis's verdict identical across
    all K runs? (per-axis all-agree rate + the flips).
  * MedDRA stability — same PT across runs.
  * Accuracy variance vs gold — per-axis agreement mean and range across the K runs,
    and the SAFETY headline: was the under-call count 0 in EVERY run?

Usage (project venv):  ../venv/Scripts/python.exe experiments/scripts/triage_robustness.py [K]
Default K=3. More runs = tighter variance but more API cost (K x 5 cases).
Single snapshot; gold is the interim hand-authored set (see data/gold/).
"""

import json
import os
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["PAST_CASES_RUNTIME_DIR"] = str(ROOT / "backend" / ".robust_pc_runtime")
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

GOLD_DIR = ROOT / "data" / "gold"
SAMPLE_DIR = ROOT / "data" / "sample_reports"
OUT = ROOT / "experiments" / "triage_robustness.md"
K = int(sys.argv[1]) if len(sys.argv) > 1 else 3
SER_ORDER = {"非重篤": 0, "要確認": 1, "重篤": 2}


def norm(s):
    return unicodedata.normalize("NFKC", (s or "").strip())


def load_gold():
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(GOLD_DIR.glob("*.gold.json"))]


def run(client, doc):
    content = (SAMPLE_DIR / doc).read_bytes()
    r = client.post("/cases/triage", params={"auto_approve": "true", "influence": "advisory"},
                    files={"file": (doc, content, "text/plain")})
    r.raise_for_status()
    return r.json()


def index(data):
    return {
        "ser": {norm(s["term"]): s["verdict"] for s in data["seriousness"]},
        "cau": {norm(c["term"]): c["verdict"] for c in data["causality"]},
        "med": {norm(m["term"]): m.get("pt_code") for m in data["meddra"]},
        "exp": {norm(a["term"]): a["verdict"]
                for de in data.get("expectedness", []) for a in de["assessments"]},
        "terms": [norm(ae["term"]) for ae in data["extraction"]["adverse_events"]],
    }


def match(gterm, terms):
    g = norm(gterm)
    if g in terms:
        return g
    for t in terms:
        if g and (g in t or t in g):
            return t
    return None


def score_run(gold, runs_by_doc_single):
    """Agreement + under-call for a single run-map {doc: index}."""
    agg = {"ser_a": 0, "ser_t": 0, "ser_u": 0, "cau_a": 0, "cau_t": 0, "cau_u": 0,
           "exp_a": 0, "exp_t": 0, "exp_u": 0, "med_h": 0, "med_t": 0}
    for gc in gold:
        sysd = runs_by_doc_single[gc["document"]]
        for ev in gc["events"]:
            mt = match(ev["term"], sysd["terms"])
            if not mt:
                continue
            if ev.get("pt_codes"):
                agg["med_t"] += 1
                agg["med_h"] += sysd["med"].get(mt) in ev["pt_codes"]
            gs, ss = ev.get("seriousness"), sysd["ser"].get(mt)
            if gs and ss:
                agg["ser_t"] += 1
                agg["ser_a"] += gs == ss
                agg["ser_u"] += SER_ORDER.get(ss, 0) < SER_ORDER.get(gs, 0)
            gcv, scv = ev.get("causality"), sysd["cau"].get(mt)
            if gcv and scv:
                agg["cau_t"] += 1
                agg["cau_a"] += gcv == scv
                agg["cau_u"] += (gcv == "否定できない" and scv == "否定できる")
            for _drug, gv in (ev.get("expectedness") or {}).items():
                sv = sysd["exp"].get(mt)
                if sv is None:
                    continue
                agg["exp_t"] += 1
                agg["exp_a"] += gv == sv
                agg["exp_u"] += (gv == "未知" and sv == "既知")
    return agg


def main():
    gold = load_gold()
    # runs[k][doc] = index
    runs = [dict() for _ in range(K)]
    with TestClient(app) as client:
        for gc in gold:
            for k in range(K):
                runs[k][gc["document"]] = index(run(client, gc["document"]))

    lines = [f"# ロバスト性（run-to-run 変動） — K={K} 回実行\n"]
    lines.append("> 素判定(advisory)をK回実行（influenceは決定論なので変動はLLM由来）。単一スナップショット、")
    lines.append("> ゴールドは暫定起案。`experiments/scripts/triage_robustness.py [K]` で再現。\n")

    # --- extraction + verdict + MedDRA stability ---
    lines.append("## 抽出・判定・MedDRAの安定性\n")
    lines.append("| 症例 | 全K回に出た事象 | ゆらいだ抽出 | 重篤度 全一致 | 因果 全一致 | 既知未知 全一致 | PT 全一致 |")
    lines.append("|---|---|---|---|---|---|---|")
    tot = defaultdict(lambda: [0, 0])  # axis -> [stable, total]
    for gc in gold:
        doc = gc["document"]
        term_runs = [set(runs[k][doc]["terms"]) for k in range(K)]
        common = set.intersection(*term_runs)
        union = set.union(*term_runs)
        flaky = union - common

        def all_agree(field):
            stable = 0
            for t in common:
                vals = {runs[k][doc][field].get(t) for k in range(K)}
                stable += len(vals) == 1
                tot[field][0] += len(vals) == 1
                tot[field][1] += 1
            return f"{stable}/{len(common)}" if common else "—"

        row = [doc, f"{len(common)}", ("、".join(sorted(flaky)) or "—"),
               all_agree("ser"), all_agree("cau"), all_agree("exp"), all_agree("med")]
        lines.append("| " + " | ".join(row) + " |")

    def rate(field):
        s, t = tot[field]
        return f"{100*s/t:.0f}% ({s}/{t})" if t else "—"
    lines.append("")
    lines.append(f"- 全K一致率（安定事象のみ）: 重篤度 **{rate('ser')}** / 因果 **{rate('cau')}** / "
                 f"既知未知 **{rate('exp')}** / MedDRA PT **{rate('med')}**")

    # --- accuracy variance + safety across runs ---
    per_run = [score_run(gold, runs[k]) for k in range(K)]

    def pct_range(a_key, t_key):
        vals = [100 * r[a_key] / r[t_key] if r[t_key] else 0 for r in per_run]
        return f"{sum(vals)/len(vals):.0f}% （{min(vals):.0f}–{max(vals):.0f}）"

    def under_all_zero(u_key):
        us = [r[u_key] for r in per_run]
        return f"{'✅ 全runで0' if max(us) == 0 else '⚠️ ' + str(max(us))}（各run: {us}）"

    lines.append("")
    lines.append("## 精度のばらつき（対ゴールド, K回の平均と幅）\n")
    lines.append("| 指標 | 平均（最小–最大） |")
    lines.append("|---|---|")
    lines.append(f"| MedDRA PT 完全一致 | {pct_range('med_h', 'med_t')} |")
    lines.append(f"| 重篤度 一致 | {pct_range('ser_a', 'ser_t')} |")
    lines.append(f"| 因果 一致 | {pct_range('cau_a', 'cau_t')} |")
    lines.append(f"| 既知/未知 一致 | {pct_range('exp_a', 'exp_t')} |")
    lines.append("")
    lines.append("## 安全側の安定性（過小コールがK回すべてで0か）\n")
    lines.append(f"- 重篤度 過小: {under_all_zero('ser_u')}")
    lines.append(f"- 因果 過小: {under_all_zero('cau_u')}")
    lines.append(f"- 既知/未知 過小: {under_all_zero('exp_u')}")
    lines.append("")
    lines.append("> 解釈: 抽出はナラティブ由来事象で多少ゆらぐ一方、**判定軸の全一致率**と**過小0の維持**が")
    lines.append("> 安定性の要点。K/症例数が小さい点は限界（[[triage_eval.md]] 限界節と同じ）。")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)
    print("stability ser/cau/exp/med:", rate("ser"), rate("cau"), rate("exp"), rate("med"))
    print("under-call max across runs ser/cau/exp:",
          max(r["ser_u"] for r in per_run), max(r["cau_u"] for r in per_run),
          max(r["exp_u"] for r in per_run))


if __name__ == "__main__":
    main()
