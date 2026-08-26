"""Embedding-provider retrieval benchmark (Phase 5a).

Isolates the *embedding* contribution to MedDRA PT retrieval, with NO LLM in the
loop, so the A/B is deterministic and attributable purely to the embedding model
(OpenAI text-embedding-3-small vs a local model served by Ollama, e.g. bge-m3).

For every gold adverse-event term (in-scope cases only) we ask: does the correct
MedDRA PT appear in the top-k candidates? We report this two ways per provider:

  - hybrid   : exact ⊕ char-bigram BM25 ⊕ vector, RRF-fused (what the system uses).
  - vector   : dense-vector search alone (isolates the embedding's own quality).

...and separately on the HARD subset — terms with NO exact dictionary match, where
lexical signals can't carry the case and the embedding actually decides. That hard
subset is where a local embedding must hold up. We also time query embedding/search
latency (local GPU vs cloud round-trip) and one-time index build time.

Run (project venv), from the repo root:
    ./venv/Scripts/python.exe experiments/scripts/embedding_retrieval_bench.py

Writes experiments/embedding_retrieval_bench.md. Reproducible; deterministic
(retrieval only — no LLM). Requires Ollama running with the local model pulled.
"""

import json
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# Console may be cp932 on Windows; keep JP readable in stdout (file output is utf-8).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from langchain_openai import OpenAIEmbeddings  # noqa: E402
from langchain_ollama import OllamaEmbeddings  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.meddra import MeddraDictionary  # noqa: E402
from app.services.meddra_retriever import HybridMeddraRetriever  # noqa: E402

GOLD_DIR = ROOT / "data" / "gold"
OUT = ROOT / "experiments" / "embedding_retrieval_bench.md"
BENCH_DIR = ROOT / "backend" / ".embed_bench"
TOP_KS = (1, 3, 5)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip())


def load_gold_terms():
    """Return [(document, term, [pt_codes])] over in-scope gold events only."""
    rows = []
    for f in sorted(GOLD_DIR.glob("*.gold.json")):
        gc = json.loads(f.read_text(encoding="utf-8"))
        if gc.get("out_of_scope"):
            continue
        for ev in gc["events"]:
            codes = ev.get("pt_codes", [])
            if codes:
                rows.append((gc["document"], ev["term"], codes))
    return rows


def build_embeddings():
    """The two providers under test (constructed directly, bypassing the DI cache)."""
    return {
        "openai": (
            settings.openai_embedding_model,
            OpenAIEmbeddings(
                model=settings.openai_embedding_model,
                api_key=settings.openai_api_key,
            ),
        ),
        "ollama": (
            settings.ollama_embedding_model,
            OllamaEmbeddings(
                model=settings.ollama_embedding_model,
                base_url=settings.ollama_base_url,
            ),
        ),
    }


def hit_at(codes_ranked, gold_codes, k):
    return any(c in gold_codes for c in codes_ranked[:k])


def eval_provider(provider, model_name, embeddings, dic, terms):
    persist = str(BENCH_DIR / f"{provider}__{model_name}".replace(":", "-").replace("/", "-"))
    retriever = HybridMeddraRetriever(
        dictionary=dic,
        embeddings=embeddings,
        persist_dir=persist,
        collection_name=settings.meddra_collection_name,
    )
    t0 = time.perf_counter()
    added = retriever.ensure_indexed()
    index_ms = (time.perf_counter() - t0) * 1000 if added else None

    dim = len(embeddings.embed_query("次元確認"))

    # Warm up (model load into VRAM + HNSW touch) so query latency reflects steady
    # state, not the one-time cold start. index_ms below still includes first load.
    for _ in range(3):
        retriever.store.similarity_search("ウォームアップ", k=max(TOP_KS))

    per_term = []
    latencies = []
    for doc, term, gold in terms:
        exact = bool(dic.exact_matches(term))
        hybrid_codes = [t.pt_code for t in retriever.search(term, top_k=max(TOP_KS))]
        t1 = time.perf_counter()
        vec_docs = retriever.store.similarity_search(term, k=max(TOP_KS))
        latencies.append((time.perf_counter() - t1) * 1000)
        vector_codes = [d.metadata.get("pt_code") for d in vec_docs]
        per_term.append({
            "doc": doc, "term": term, "gold": gold, "exact": exact,
            "hybrid": {k: hit_at(hybrid_codes, gold, k) for k in TOP_KS},
            "vector": {k: hit_at(vector_codes, gold, k) for k in TOP_KS},
            "vector_top": vector_codes,
        })
    return {
        "provider": provider, "model": model_name, "dim": dim,
        "index_ms": index_ms, "mean_latency_ms": sum(latencies) / len(latencies),
        "per_term": per_term,
    }


def agg_hits(per_term, mode, subset=None):
    rows = [p for p in per_term if subset is None or subset(p)]
    n = len(rows)
    return n, {k: sum(1 for p in rows if p[mode][k]) for k in TOP_KS}


def pct(n, d):
    return f"{100*n/d:.0f}% ({n}/{d})" if d else "—"


def main():
    dic = MeddraDictionary(csv_path=settings.meddra_path)
    terms = load_gold_terms()
    embs = build_embeddings()

    results = {}
    unavailable = {}
    for provider, (model_name, emb) in embs.items():
        print(f"evaluating {provider}:{model_name} ...")
        try:
            results[provider] = eval_provider(provider, model_name, emb, dic, terms)
        except Exception as exc:  # noqa: BLE001 - one provider failing must not sink the bench
            msg = str(exc).splitlines()[0][:200]
            unavailable[provider] = f"{model_name}: {msg}"
            print(f"  !! {provider} unavailable: {msg}")

    n_exact = sum(1 for _, t, _ in terms if dic.exact_matches(t))
    n_hard = len(terms) - n_exact
    order = [p for p in ("openai", "ollama") if p in results]

    L = []
    L.append("# 埋め込みプロバイダ 検索ベンチ（Phase 5a）\n")
    L.append("> LLM非依存・決定的。gold事象語 → 正解MedDRA PT が top-k に入るか（hit@k）を、")
    L.append("> hybrid（exact⊕BM25⊕vector）と vector単独（埋め込み単体の質）で比較。`hard`=exact一致なし")
    L.append("> の難語サブセット＝埋め込みが実際に効く領域。`experiments/scripts/embedding_retrieval_bench.py` で再現。\n")
    L.append(f"- 対象: in-scope gold **{len(terms)}事象**（うち exact一致 {n_exact}／**hard(exact無) {n_hard}**）")
    provs = "、".join(f"{p} `{results[p]['model']}`({results[p]['dim']}次元)" for p in order)
    L.append(f"- プロバイダ: {provs}")
    if unavailable:
        for p, why in unavailable.items():
            L.append(f"- ⚠️ **{p} は今回計測不可**（{why}）")
    L.append("")

    def hit_table(title, subset, subset_desc):
        L.append(f"## {title}（{subset_desc}）\n")
        L.append("| プロバイダ | hybrid@1 | hybrid@3 | hybrid@5 | vector@1 | vector@3 | vector@5 |")
        L.append("|---|---|---|---|---|---|---|")
        for p in order:
            pt = results[p]["per_term"]
            nh, h = agg_hits(pt, "hybrid", subset)
            nv, v = agg_hits(pt, "vector", subset)
            L.append(
                f"| {p} `{results[p]['model']}` | "
                + " | ".join(pct(h[k], nh) for k in TOP_KS) + " | "
                + " | ".join(pct(v[k], nv) for k in TOP_KS) + " |"
            )
        L.append("")

    hit_table("全事象", None, f"n={len(terms)}")
    hit_table("hard サブセット", lambda p: not p["exact"], f"exact一致なし n={n_hard}")

    L.append("## レイテンシ・インデックス構築\n")
    L.append("| プロバイダ | クエリ検索 平均(ms) | インデックス構築(ms, 56PT) |")
    L.append("|---|---|---|")
    for p in order:
        r = results[p]
        idx = f"{r['index_ms']:.0f}" if r["index_ms"] is not None else "（既存・再利用）"
        L.append(f"| {p} `{r['model']}` | {r['mean_latency_ms']:.1f} | {idx} |")
    L.append("")

    # Disagreements on the hard subset: vector@3 differs between providers.
    if len(order) == 2:
        L.append("## vector@3 の食い違い（hard サブセット）\n")
        dis = []
        for a, b in zip(results[order[0]]["per_term"], results[order[1]]["per_term"]):
            if a["exact"]:
                continue
            if a["vector"][3] != b["vector"][3]:
                winner = order[0] if a["vector"][3] else order[1]
                dis.append((a["doc"], a["term"], a["gold"], winner))
        if dis:
            L.append(f"| 症例 | 事象 | 正解PT | vector@3で当てた側 |")
            L.append("|---|---|---|---|")
            for doc, term, gold, w in dis:
                L.append(f"| {doc} | {term} | {'/'.join(gold)} | **{w}** |")
        else:
            L.append("_（hard サブセットで vector@3 の差異なし）_")
        L.append("")

    # Single-provider run: show which hard terms the vector search misses (@3).
    if len(order) == 1:
        p = order[0]
        L.append(f"## {p} vector@3 が外した hard 事象\n")
        misses = [x for x in results[p]["per_term"] if not x["exact"] and not x["vector"][3]]
        if misses:
            L.append("| 症例 | 事象 | 正解PT |")
            L.append("|---|---|---|")
            for x in misses:
                L.append(f"| {x['doc']} | {x['term']} | {'/'.join(x['gold'])} |")
        else:
            L.append("_（hard サブセットは全て vector@3 で命中）_")
        L.append("")

    L.append("## 読み方（限界）\n")
    L.append("- これは**検索の質**のみ（埋め込み単体を分離）。実運用の最終精度は後段LLMのcandidate選択に依存＝別途end-to-endで測る。")
    L.append("- exact/BM25 が効く語では埋め込みは無関係。差が出るのは **hard サブセット**。標本が小さいので百分率は高分散。")
    L.append("- hybrid は exact⊕BM25 を含むため、vector単独が弱くても hybrid は保たれ得る（＝ローカル埋め込みの弱さを字句が吸収する構造）。")
    L.append("- **クエリ検索レイテンシは3回warmup後の定常値**（初回VRAMロードを除外）。インデックス構築(ms)は初回モデルロードを含む一回限りコスト。ローカルはGPU、OpenAIはネットワーク往復。")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print("wrote", OUT)
    for p in order:
        pt = results[p]["per_term"]
        _, h = agg_hits(pt, "hybrid", None)
        nhard, vh = agg_hits(pt, "vector", lambda x: not x["exact"])
        print(f"{p}: hybrid@1={h[1]}/{len(pt)}  vector@3(hard)={vh[3]}/{nhard}  "
              f"latency={results[p]['mean_latency_ms']:.1f}ms")


if __name__ == "__main__":
    main()
