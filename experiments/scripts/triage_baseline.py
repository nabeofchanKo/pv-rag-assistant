"""Baseline comparison (E2 of the rigorous eval).

A naive **single-LLM-call** triage (one structured shot: extract events + guess a
MedDRA PT code + seriousness + causality + 既知/未知) with NO decomposition, NO
retrieval (no drug label, no MedDRA dictionary), NO deterministic rules, NO
IME/precedent. Scored against gold next to the multi-step pipeline (advisory), to
show whether the pipeline's extra machinery earns its complexity.

Uses gpt-4o for the baseline (the strongest model the pipeline also uses) so the
comparison isolates ARCHITECTURE, not model size. Single-run snapshot; interim gold.

Usage:  ../venv/Scripts/python.exe experiments/scripts/triage_baseline.py
"""

import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
os.environ["PAST_CASES_RUNTIME_DIR"] = str(ROOT / "backend" / ".baseline_pc")
sys.path.insert(0, str(ROOT / "backend"))

from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.config import settings  # noqa: E402

GOLD_DIR = ROOT / "data" / "gold"
SAMPLE_DIR = ROOT / "data" / "sample_reports"
OUT = ROOT / "experiments" / "triage_baseline.md"
SER_ORDER = {"非重篤": 0, "要確認": 1, "重篤": 2}

BASELINE_PROMPT = (
    "あなたは医薬品安全性監視(PV)の担当者です。以下の症例テキストから、有害事象トリアージを"
    "一度で行ってください。各有害事象について：\n"
    "1) 事象名（term、報告・経過の両方から。過去の無関係な事象は含めない）\n"
    "2) MedDRA PTコード（あなたの知識で最も近いPTの数字コード。不明ならnull）\n"
    "3) 企業重篤度（ICH E2A: 重篤/非重篤/要確認。重症度≠重篤性）\n"
    "4) 因果関係（保守的な時間的評価: 否定できない/否定できる/評価不能）\n"
    "5) 既知/未知（一般的な添付文書知識に照らして: 既知/未知/要確認/判定不能。自社品でなければnull）\n"
    "症例テキスト:\n{case}"
)


class BaselineEvent(BaseModel):
    term: str
    pt_code: str | None = Field(default=None, description="MedDRA PTの数字コード（不明ならnull）")
    seriousness: Literal["重篤", "非重篤", "要確認"]
    causality: Literal["否定できない", "否定できる", "評価不能"]
    expectedness: Literal["既知", "未知", "要確認", "判定不能"] | None = None


class BaselineTriage(BaseModel):
    events: list[BaselineEvent]


def norm(s):
    return unicodedata.normalize("NFKC", (s or "").strip())


def load_gold():
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(GOLD_DIR.glob("*.gold.json"))]


def match(gterm, terms):
    g = norm(gterm)
    if g in terms:
        return g
    return next((t for t in terms if g and (g in t or t in g)), None)


def score(gold, sysmap):
    """sysmap: {doc: {ser,cau,exp,med(term->pt),terms}} -> aggregate metrics."""
    a = {k: 0 for k in ("med_h", "med_t", "ser_a", "ser_t", "ser_u", "cau_a", "cau_t",
                        "cau_u", "exp_a", "exp_t", "exp_u", "rec_h", "rec_t", "extra")}
    for gc in gold:
        s = sysmap[gc["document"]]
        matched = set()
        for ev in gc["events"]:
            a["rec_t"] += 1
            mt = match(ev["term"], s["terms"])
            if not mt:
                continue
            matched.add(mt)
            a["rec_h"] += 1
            if ev.get("pt_codes"):
                a["med_t"] += 1
                a["med_h"] += s["med"].get(mt) in ev["pt_codes"]
            gs, ss = ev.get("seriousness"), s["ser"].get(mt)
            if gs and ss:
                a["ser_t"] += 1; a["ser_a"] += gs == ss
                a["ser_u"] += SER_ORDER.get(ss, 0) < SER_ORDER.get(gs, 0)
            gc_, sc_ = ev.get("causality"), s["cau"].get(mt)
            if gc_ and sc_:
                a["cau_t"] += 1; a["cau_a"] += gc_ == sc_
                a["cau_u"] += (gc_ == "否定できない" and sc_ == "否定できる")
            for _d, gv in (ev.get("expectedness") or {}).items():
                sv = s["exp"].get(mt)
                if sv is None:
                    continue
                a["exp_t"] += 1; a["exp_a"] += gv == sv
                a["exp_u"] += (gv == "未知" and sv == "既知")
        a["extra"] += len([t for t in s["terms"] if t not in matched])
    return a


def main():
    gold = [g for g in load_gold() if not g.get("out_of_scope")]  # verdict-based: skip out-of-scope
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=settings.openai_api_key)
    chain = llm.with_structured_output(BaselineTriage)

    base_map, pipe_map = {}, {}
    with TestClient(app) as client:
        for gc in gold:
            doc = gc["document"]
            text = (SAMPLE_DIR / doc).read_text(encoding="utf-8")
            # baseline: one LLM call
            bt = chain.invoke(BASELINE_PROMPT.format(case=text))
            base_map[doc] = {
                "ser": {norm(e.term): e.seriousness for e in bt.events},
                "cau": {norm(e.term): e.causality for e in bt.events},
                "exp": {norm(e.term): e.expectedness for e in bt.events if e.expectedness},
                "med": {norm(e.term): e.pt_code for e in bt.events},
                "terms": [norm(e.term) for e in bt.events],
            }
            # pipeline: advisory (fresh)
            r = client.post("/cases/triage", params={"auto_approve": "true", "influence": "advisory"},
                            files={"file": (doc, text.encode("utf-8"), "text/plain")})
            r.raise_for_status()
            d = r.json()
            pipe_map[doc] = {
                "ser": {norm(s["term"]): s["verdict"] for s in d["seriousness"]},
                "cau": {norm(c["term"]): c["verdict"] for c in d["causality"]},
                "exp": {norm(x["term"]): x["verdict"] for de in d["expectedness"] for x in de["assessments"]},
                "med": {norm(m["term"]): m.get("pt_code") for m in d["meddra"]},
                "terms": [norm(ae["term"]) for ae in d["extraction"]["adverse_events"]],
            }

    b, p = score(gold, base_map), score(gold, pipe_map)

    def pct(agg, hk, tk):
        return f"{100*agg[hk]/agg[tk]:.0f}% ({agg[hk]}/{agg[tk]})" if agg[tk] else "—"

    lines = ["# ベースライン対比（単一LLM 1回 vs 多段パイプライン）\n"]
    lines.append("> ベースライン=gpt-4oに1回で全トリアージを構造化出力（分解/RAG/決定論/IME/precedentなし）。")
    lines.append("> パイプライン=advisory(素判定)。同一ゴールド・単一実行。`triage_baseline.py` で再現。\n")
    lines.append("| 指標 | ベースライン(1回LLM) | パイプライン(多段) |")
    lines.append("|---|---|---|")
    lines.append(f"| MedDRA PT 完全一致 | {pct(b,'med_h','med_t')} | {pct(p,'med_h','med_t')} |")
    lines.append(f"| 重篤度 一致 | {pct(b,'ser_a','ser_t')} | {pct(p,'ser_a','ser_t')} |")
    lines.append(f"| 　└ 過小コール | {b['ser_u']} | {p['ser_u']} |")
    lines.append(f"| 因果 一致 | {pct(b,'cau_a','cau_t')} | {pct(p,'cau_a','cau_t')} |")
    lines.append(f"| 　└ 過小コール | {b['cau_u']} | {p['cau_u']} |")
    lines.append(f"| 既知/未知 一致 | {pct(b,'exp_a','exp_t')} | {pct(p,'exp_a','exp_t')} |")
    lines.append(f"| 　└ 過小コール | {b['exp_u']} | {p['exp_u']} |")
    lines.append(f"| 抽出 recall | {pct(b,'rec_h','rec_t')} | {pct(p,'rec_h','rec_t')} |")
    lines.append(f"| 余分抽出 | {b['extra']} | {p['extra']} |")
    lines.append("")
    lines.append("## 解釈\n")
    lines.append("- **MedDRA**: ベースラインは辞書拘束が無く、PTコードを幻覚・不一致しやすい（パイプラインは")
    lines.append("  辞書＋ハイブリッド検索で拘束）。既知/未知も、ベースラインは添付文書RAGが無く当て推量。")
    lines.append("- **過小コール**: パイプラインは決定論OR＋安全側で過小を抑える設計。ベースラインの過小の有無が")
    lines.append("  安全性の差を示す。限界: 小規模・単一実行・gold自作（[[triage_eval.md]] 限界節と同じ）。")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)
    print("baseline meddra/ser_u/exp_u:", pct(b, 'med_h', 'med_t'), b['ser_u'], b['exp_u'])
    print("pipeline meddra/ser_u/exp_u:", pct(p, 'med_h', 'med_t'), p['ser_u'], p['exp_u'])


if __name__ == "__main__":
    main()
