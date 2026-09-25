"""Per-step generation-model comparison bench (Phase 5b).

Full end-to-end triage on a local 7B is impractical (~10-15 min/case: the pipeline
makes ~40 sequential structured-output calls per case). So we benchmark each STEP
in isolation over the gold set — which is also exactly the "where does a local model
hold vs break, per step" question 5b set out to answer.

For each candidate chat model (OpenAI baseline, or a local model via Ollama) we run,
step by step, on the in-scope gold events and score against gold:

  extraction   — recall of gold event terms, false-positive extras, and two quality
                 signals a weak model trips on: English MedDRA name leaked into the
                 term (prompt says to drop it) and a garbled patient age field.
  meddra       — MedDRA PT exact-match (overall + on the LLM-selection subset, since
                 exact dictionary hits are deterministic and don't test the model).
  seriousness  — verdict agreement + safety-critical UNDER-calls (system < gold).
  causality    — agreement + UNDER-calls (gold 否定できない but system 否定できる).
  expectedness — agreement + UNDER-calls (gold 未知 but system 既知).

Every step is timed and every per-item call is guarded, so a structured-output
failure is counted (not fatal). Embeddings are held at OpenAI for every model, so
the A/B isolates the GENERATION model (retrieval is constant; see Phase 5a for the
embedding A/B). Generation runs at temperature 0 but LLMs are not fully
deterministic — single-run snapshot.

Run (project venv), from the repo root:
    ./venv/Scripts/python.exe experiments/scripts/generation_bench.py
Adding a model = one entry in MODELS. A local model must be pulled in Ollama first.
Writes experiments/generation_comparison.md.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
OUT = ROOT / "experiments" / "generation_comparison.md"
RESULT_MARKER = "@@RESULT@@"
# A single structured-output call must not hang the whole bench (a local model can
# wedge an HTTP request). Bound each call; on timeout it is counted as a failure and
# the bench moves on (the stuck daemon thread dies with the process). 60s is generous
# for a real call (~10-30s) while catching a hang faster (a weak model can hang ~half
# its calls, so timeout x #calls dominates the multi-model wall-clock).
CALL_TIMEOUT_S = 60


def _call_with_timeout(fn, timeout):
    """Run fn in a daemon thread; return (result, error). error is set on exception
    or timeout. Daemon so a wedged call can't block process exit."""
    box = {}

    def run():
        try:
            box["result"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = str(exc).splitlines()[0][:160]

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        return None, f"timeout>{timeout}s"
    return box.get("result"), box.get("error")

# Candidate chat models. `env` is layered onto the worker subprocess; embeddings are
# left at their default (OpenAI) so only generation varies. Add a model = add a row.
MODELS = [
    {"label": "openai (baseline, per-step 4o/mini)", "env": {"CHAT_PROVIDER": "openai"}},
    {"label": "qwen2.5:7b", "env": {"CHAT_PROVIDER": "ollama", "OLLAMA_CHAT_MODEL": "qwen2.5:7b"}},
    {"label": "ELYZA-JP-8B", "env": {"CHAT_PROVIDER": "ollama",
        "OLLAMA_CHAT_MODEL": "hf.co/elyza/Llama-3-ELYZA-JP-8B-GGUF:latest"}},
    {"label": "gemma3:4b", "env": {"CHAT_PROVIDER": "ollama", "OLLAMA_CHAT_MODEL": "gemma3:4b"}},
    {"label": "medllama2 (医療特化/Llama2系)", "env": {"CHAT_PROVIDER": "ollama",
        "OLLAMA_CHAT_MODEL": "medllama2"}},
]

SER_ORDER = {"非重篤": 0, "要確認": 1, "重篤": 2}
DRUG_LABEL = {"DrugX": "drugx_label.md", "DrugY": "drugy_label.md", "DrugZ": "drugz_label.md"}


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip())


def load_gold():
    cases = []
    for f in sorted(GOLD_DIR.glob("*.gold.json")):
        gc = json.loads(f.read_text(encoding="utf-8"))
        if not gc.get("out_of_scope"):
            cases.append(gc)
    return cases


def match_term(gold_term, system_terms):
    g = norm(gold_term)
    if g in system_terms:
        return g
    for t in system_terms:
        if g and (g in t or t in g):
            return t
    return None


# --------------------------------------------------------------------------- #
# Worker: runs in a subprocess with CHAT_PROVIDER/OLLAMA_CHAT_MODEL already set #
# --------------------------------------------------------------------------- #

def _progress(msg):
    print(msg, file=sys.stderr, flush=True)


def run_worker(steps, max_events):
    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import settings
    from app.schemas import AdverseEventMention
    from app.dependencies import (
        get_extraction_service, get_meddra_coding_service, get_seriousness_service,
        get_causality_service, get_expectedness_service, get_meddra_retriever,
        get_label_index_service, get_extraction_model,
    )

    model_id = (
        settings.ollama_chat_model if settings.chat_provider == "ollama"
        else f"openai per-step ({settings.openai_seriousness_model}/{settings.openai_meddra_model})"
    )
    _progress(f"[worker] provider={settings.chat_provider} model={model_id}")

    # Reference collections must be indexed (normally done by the app lifespan).
    get_meddra_retriever().ensure_indexed()
    get_label_index_service().ensure_indexed()

    # Warm up the local model (load weights into VRAM) so latencies are steady-state.
    if settings.chat_provider == "ollama":
        _progress("[worker] warming up local model ...")
        get_extraction_model().invoke("ウォームアップ")

    gold = load_gold()
    case_text = {gc["document"]: (ROOT / "data" / "sample_reports" / gc["document"]).read_text(encoding="utf-8")
                 for gc in gold}
    # Flat list of (document, event) across in-scope cases, optionally capped.
    events = [(gc["document"], ev) for gc in gold for ev in gc["events"]]
    if max_events:
        events = events[:max_events]

    out = {"model": model_id, "steps": {}}

    def timed(fn):
        # A structured-output failure OR a hang is data, not fatal — bound + count it.
        t0 = time.perf_counter()
        result, err = _call_with_timeout(fn, CALL_TIMEOUT_S)
        return result, (time.perf_counter() - t0), err

    # -- extraction (per case) --
    if "extraction" in steps:
        svc = get_extraction_service()
        rec_hit = rec_tot = extra = eng_leak = age_bad = fails = 0
        lat = []
        for gc in gold:
            _progress(f"[extraction] {gc['document']}")
            res, dt, err = timed(lambda: svc.extract(case_text[gc["document"]]))
            lat.append(dt)
            if err:
                fails += 1
                continue
            sys_terms = [norm(ae.term) for ae in res.adverse_events]
            matched = set()
            for ev in gc["events"]:
                rec_tot += 1
                mt = match_term(ev["term"], sys_terms)
                if mt:
                    rec_hit += 1
                    matched.add(mt)
            extra += len([t for t in sys_terms if t not in matched])
            eng_leak += sum(1 for t in sys_terms if any("a" <= c.lower() <= "z" for c in t))
            age = (res.patient.age or "")
            if age and any(c not in "0123456789 歳代半ば約" for c in norm(age)):
                age_bad += 1
        out["steps"]["extraction"] = {
            "recall_hit": rec_hit, "recall_total": rec_tot, "extra": extra,
            "eng_leak": eng_leak, "age_bad": age_bad, "fails": fails,
            "latency_ms": sum(lat) / len(lat) * 1000 if lat else 0,
        }

    # -- meddra (per event term) --
    if "meddra" in steps:
        svc = get_meddra_coding_service()
        hit = tot = llm_hit = llm_tot = none_cnt = fails = 0
        lat = []
        for doc, ev in events:
            _progress(f"[meddra] {ev['term']}")
            res, dt, err = timed(lambda: svc.code([ev["term"]])[0])
            lat.append(dt)
            if err:
                fails += 1
                continue
            tot += 1
            ok = res.pt_code in ev.get("pt_codes", [])
            hit += ok
            if res.coded_by != "完全一致":  # the subset the model actually decides
                llm_tot += 1
                llm_hit += ok
            if res.coded_by == "該当なし":
                none_cnt += 1
        out["steps"]["meddra"] = {
            "hit": hit, "total": tot, "llm_hit": llm_hit, "llm_total": llm_tot,
            "none": none_cnt, "fails": fails, "latency_ms": sum(lat) / len(lat) * 1000 if lat else 0,
        }

    # -- seriousness / causality (per event) --
    for step, key, build in (
        ("seriousness", "seriousness", get_seriousness_service),
        ("causality", "causality", get_causality_service),
    ):
        if step not in steps:
            continue
        svc = build()
        agree = tot = under = over = fails = 0
        lat = []
        for doc, ev in events:
            goldv = ev.get(key)
            if not goldv:
                continue
            ae = AdverseEventMention(term=ev["term"], source="reported")
            _progress(f"[{step}] {ev['term']}")
            res, dt, err = timed(lambda: svc.assess(case_text[doc], [ae])[0])
            lat.append(dt)
            if err:
                fails += 1
                continue
            tot += 1
            sysv = res.verdict
            if sysv == goldv:
                agree += 1
            elif step == "seriousness":
                if SER_ORDER.get(sysv, 0) < SER_ORDER.get(goldv, 0):
                    under += 1
                else:
                    over += 1
            elif step == "causality":
                if goldv == "否定できない" and sysv == "否定できる":
                    under += 1
                else:
                    over += 1
        out["steps"][step] = {
            "agree": agree, "total": tot, "under": under, "over": over,
            "fails": fails, "latency_ms": sum(lat) / len(lat) * 1000 if lat else 0,
        }

    # -- expectedness (per event x own-company drug) --
    if "expectedness" in steps:
        svc = get_expectedness_service()
        agree = tot = under = over = fails = 0
        lat = []
        for doc, ev in events:
            for drug, goldv in (ev.get("expectedness") or {}).items():
                label = DRUG_LABEL.get(drug)
                if not label:
                    continue
                _progress(f"[expectedness] {ev['term']} / {drug}")
                res, dt, err = timed(lambda: svc.assess(drug, label, [ev["term"]]).assessments[0])
                lat.append(dt)
                if err:
                    fails += 1
                    continue
                tot += 1
                sysv = res.verdict
                if sysv == goldv:
                    agree += 1
                elif goldv == "未知" and sysv == "既知":
                    under += 1
                else:
                    over += 1
        out["steps"]["expectedness"] = {
            "agree": agree, "total": tot, "under": under, "over": over,
            "fails": fails, "latency_ms": sum(lat) / len(lat) * 1000 if lat else 0,
        }

    print(RESULT_MARKER + json.dumps(out, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Parent: spawn one worker per model, aggregate, write the comparison report    #
# --------------------------------------------------------------------------- #

def pct(n, d):
    return f"{100*n/d:.0f}% ({n}/{d})" if d else "—"


def run_parent(steps, max_events):
    results = []
    for m in MODELS:
        _progress(f"\n=== {m['label']} ===")
        # Force utf-8 on the child's stdio (Windows consoles default to cp932, which
        # would corrupt the JP progress/result stream the parent decodes as utf-8).
        env = {**os.environ, **m["env"], "PYTHONIOENCODING": "utf-8"}
        cmd = [sys.executable, str(Path(__file__)), "--worker", "--steps", ",".join(steps)]
        if max_events:
            cmd += ["--max-events", str(max_events)]
        # Pipe stdout (to capture the @@RESULT@@ line) but let stderr INHERIT, so the
        # worker's per-item progress streams live instead of being buffered/hidden.
        proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        line = next((l for l in (proc.stdout or "").splitlines() if l.startswith(RESULT_MARKER)), None)
        if line is None:
            _progress(f"[parent] {m['label']} produced no result (see progress above)")
            results.append({"label": m["label"], "model": "(failed)", "steps": {}})
            continue
        data = json.loads(line[len(RESULT_MARKER):])
        data["label"] = m["label"]
        results.append(data)
        _progress(f"[parent] {m['label']} done")
        # Write incrementally so the report grows as each (slow) model finishes.
        _write_report(results, steps, max_events)

    _write_report(results, steps, max_events)


def _write_report(results, steps, max_events):
    gold = load_gold()
    n_events = sum(len(gc["events"]) for gc in gold)
    if max_events:
        n_events = min(n_events, max_events)

    L = []
    L.append("# 生成モデル per-step 比較（Phase 5b）\n")
    L.append("> フルE2Eは7Bローカルで約10-15分/症例と非現実的なため、6ステップを**分離**して")
    L.append("> gold入力上で計測（＝5bの狙い「どのステップでローカルが持つ/崩れるか」に直結）。")
    L.append("> 埋め込みは全モデルOpenAI固定＝**生成のみ**のA/B（埋め込みA/Bは Phase 5a）。")
    L.append("> temperature=0だがLLMは完全決定的でない＝単一実行スナップショット。")
    L.append("> 再現: `experiments/scripts/generation_bench.py`（モデル追加は MODELS に1行）。\n")
    L.append(f"- 対象: in-scope gold {len(gold)}症例・{n_events}事象")
    L.append(f"- モデル: {'、'.join(r['label'] for r in results)}\n")

    def step_table(step, title, cols):
        if step not in steps:
            return
        L.append(f"## {title}\n")
        L.append("| モデル | " + " | ".join(c[0] for c in cols) + " | 失敗 | 平均レイテンシ |")
        L.append("|---|" + "---|" * (len(cols) + 2))
        for r in results:
            s = r["steps"].get(step)
            if not s:
                L.append(f"| {r['label']} | " + " | ".join("—" for _ in cols) + " | — | — |")
                continue
            cells = [c[1](s) for c in cols]
            lat = f"{s['latency_ms']/1000:.1f}s" if s.get("latency_ms") else "—"
            L.append(f"| {r['label']} | " + " | ".join(cells) + f" | {s['fails']} | {lat} |")
        L.append("")

    step_table("extraction", "① 抽出", [
        ("recall", lambda s: pct(s["recall_hit"], s["recall_total"])),
        ("余分抽出", lambda s: str(s["extra"])),
        ("英名混入", lambda s: str(s["eng_leak"])),
        ("age破損", lambda s: str(s["age_bad"])),
    ])
    step_table("meddra", "② MedDRA PT コード化", [
        ("PT一致(全体)", lambda s: pct(s["hit"], s["total"])),
        ("PT一致(LLM選択のみ)", lambda s: pct(s["llm_hit"], s["llm_total"])),
        ("該当なし", lambda s: str(s["none"])),
    ])
    step_table("seriousness", "③ 重篤度（企業評価 E2A）", [
        ("一致", lambda s: pct(s["agree"], s["total"])),
        ("**過小**", lambda s: f"**{s['under']}**"),
        ("過大", lambda s: str(s["over"])),
    ])
    step_table("causality", "④ 因果（時間的）", [
        ("一致", lambda s: pct(s["agree"], s["total"])),
        ("**過小(否定)**", lambda s: f"**{s['under']}**"),
    ])
    step_table("expectedness", "⑤ 既知/未知", [
        ("一致", lambda s: pct(s["agree"], s["total"])),
        ("**過小(既知)**", lambda s: f"**{s['under']}**"),
        ("過大", lambda s: str(s["over"])),
    ])

    # Safety + speed roll-up.
    L.append("## まとめ（安全側インバリアント × 速度）\n")
    L.append("| モデル | 総過小コール(重篤度+因果+既知未知) | 総失敗 | 抽出品質(英名/age) |")
    L.append("|---|---|---|---|")
    for r in results:
        s = r["steps"]
        under = sum(s.get(k, {}).get("under", 0) for k in ("seriousness", "causality", "expectedness"))
        fails = sum(v.get("fails", 0) for v in s.values())
        ex = s.get("extraction", {})
        exq = f"{ex.get('eng_leak','—')}/{ex.get('age_bad','—')}" if ex else "—"
        flag = "" if under == 0 else " ⚠️"
        L.append(f"| {r['label']} | **{under}**{flag} | {fails} | {exq} |")
    L.append("")
    L.append("## 読み方（限界）\n")
    L.append("- ステップ分離＝各ステップにgoldの正解入力を与えて計測。実運用ではステップ誤差が伝播するため、")
    L.append("  end-to-end精度はこれより低くなり得る（特に抽出漏れは後段全体に波及）。")
    L.append("- **過小コール（見落とし）が最重要**。一致率が同じでも過小の有無で安全性は大きく異なる。")
    L.append("- 標本は小規模・自作ゴールド（[EVALUATION](EVALUATION.md) の限界がそのまま該当）。単一実行。")
    L.append("- レイテンシはwarmup後の定常値。ローカルはGPU逐次、OpenAIはネットワーク並列。")

    OUT.write_text("\n".join(L), encoding="utf-8")
    _progress(f"[parent] wrote {OUT}")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--steps", default="extraction,meddra,seriousness,causality,expectedness")
    ap.add_argument("--max-events", type=int, default=0)
    args = ap.parse_args()
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    if args.worker:
        run_worker(steps, args.max_events)
    else:
        run_parent(steps, args.max_events)


if __name__ == "__main__":
    main()
