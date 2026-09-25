"""Compare MedDRA PT retrieval strategies (evidence for ADR 0003).

vector-only  vs  Level A (normalized exact/substring + vector)
             vs  Level B (BM25 char-bigram + vector, RRF-fused)

BM25 & RRF are implemented inline (no extra dependency). Makes live OpenAI
embedding calls for the 56 PT names + each query term.

Run from the repo root:
    PYTHONPATH=backend python experiments/scripts/meddra_retrieval_compare.py
(the script also puts backend/ on sys.path, so plain `python experiments/...`
works too, as long as backend/.env has OPENAI_API_KEY).
"""

import csv
import math
import pathlib
import sys
import unicodedata
from collections import Counter, defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.dependencies import get_embeddings  # noqa: E402

CSV = ROOT / "data" / "meddra_sample" / "meddra_pt.csv"
rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
ja = [r["pt_name_ja"] for r in rows]
en = [r["pt_name_en"] for r in rows]
N = len(rows)


def norm(s: str) -> str:
    return "".join(unicodedata.normalize("NFKC", s).lower().split())


def toks(s: str) -> list[str]:
    s = norm(s)
    return list(s) + [s[i : i + 2] for i in range(len(s) - 1)]


# --- dense vectors (embed the JA PT names once) ---
emb = get_embeddings()
doc_vecs = np.array(emb.embed_documents(ja))
doc_vecs /= np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-9


def vector_rank(term: str) -> list[int]:
    q = np.array(emb.embed_query(term))
    q /= np.linalg.norm(q) + 1e-9
    return list(np.argsort(-(doc_vecs @ q)))


# --- BM25 (Okapi) over character bigrams ---
corpus = [toks(t) for t in ja]
avgdl = sum(len(d) for d in corpus) / N
df: dict[str, int] = {}
for d in corpus:
    for t in set(d):
        df[t] = df.get(t, 0) + 1
idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
tfs = [Counter(d) for d in corpus]


def bm25_rank(term: str, k1=1.5, b=0.75) -> list[int]:
    qt = toks(term)
    scores = []
    for i, tf in enumerate(tfs):
        dl = len(corpus[i])
        s = sum(
            idf[t] * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
            for t in qt
            if t in idf and tf.get(t, 0)
        )
        scores.append(s)
    return list(np.argsort(-np.array(scores)))


def rrf(rankings: list[list[int]], k=60, topn=3) -> list[int]:
    score: dict[int, float] = defaultdict(float)
    for r in rankings:
        for rank, idx in enumerate(r):
            score[int(idx)] += 1 / (k + rank + 1)
    return sorted(score, key=lambda i: -score[i])[:topn]


def level_a(term: str, topn=3) -> list[int]:
    q = norm(term)
    exact = [i for i in range(N) if norm(ja[i]) == q or norm(en[i]) == q]
    substr = [i for i in range(N) if i not in exact and (q in norm(ja[i]) or norm(ja[i]) in q)]
    out = list(exact) + list(substr)
    for i in vector_rank(term):
        if int(i) not in out:
            out.append(int(i))
    return out[:topn]


def names(idxs) -> str:
    return " / ".join(ja[int(i)] for i in idxs)


TERMS = [
    "頭痛", "徐脈", "だるさ", "吐き気", "回転性めまい",
    "急性腎不全", "薬剤性肝障害", "肝機能障害", "QT延長", "血圧低下",
]

print(f"{'AE語':<8} | {'vector-only':<22} | {'Level A':<22} | Level B (BM25+vec RRF)")
print("-" * 90)
for t in TERMS:
    v = names(vector_rank(t)[:3])
    a = names(level_a(t))
    b = names(rrf([bm25_rank(t), vector_rank(t)]))
    print(f"{t:<8} | {v:<22} | {a:<22} | {b}")
