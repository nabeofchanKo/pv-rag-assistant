"""MedDRA PT dictionary + lexical ranking (the sparse half of the hybrid retriever).

MedDRA is licensed, so the repository ships only a fictional demo terminology
(DEMO-xxxx codes); a licensee points ``MEDDRA_PATH`` at their own MedDRA/J ASCII
distribution instead (ADR 0014).

Per ADR 0003, MedDRA PT retrieval fuses a lexical signal with the dense-vector
signal (RRF). This module owns the dictionary and the *lexical* half so it can be
unit-tested with no API call:

- **exact match** (NFKC-normalized) against pt_name_ja / pt_name_en — the deterministic
  fast path for the many AE terms that equal a PT verbatim;
- **BM25 over character bigrams** — no Japanese morphological analyser needed, yet
  robust to morphological variants (薬剤性↔薬物性, 障害↔異常) where dense vectors drift.

``rrf_fuse`` combines this ranking with the vector ranking (injected by the retriever
in the next slice) via Reciprocal Rank Fusion.
"""

import csv
import math
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from app.schemas import MeddraTerm


def normalize(text: str) -> str:
    """NFKC + casefold + drop whitespace, so 表記ゆれ collapses before matching."""
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def char_bigrams(text: str) -> list[str]:
    """Unigrams + bigrams of the normalized text (tokenizer for Japanese BM25)."""
    s = normalize(text)
    return list(s) + [s[i : i + 2] for i in range(len(s) - 1)]


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal Rank Fusion: merge several ranked index lists into one.

    Each item's score is the sum of 1/(k + rank) over the rankings it appears in;
    items are returned best-first. ``k`` damps the influence of low ranks.
    """
    score: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            score[idx] += 1.0 / (k + rank + 1)
    return sorted(score, key=lambda i: -score[i])


class _BM25:
    """Minimal Okapi BM25 over pre-tokenized documents (inline; no dependency)."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus_tokens
        self.n_docs = len(corpus_tokens)
        self.k1 = k1
        self.b = b
        self.avgdl = (
            sum(len(d) for d in corpus_tokens) / self.n_docs if self.n_docs else 0.0
        )
        df: dict[str, int] = {}
        for doc in corpus_tokens:
            for token in set(doc):
                df[token] = df.get(token, 0) + 1
        self.idf = {
            t: math.log(1 + (self.n_docs - n + 0.5) / (n + 0.5)) for t, n in df.items()
        }
        self.tfs = [Counter(doc) for doc in corpus_tokens]

    def rank(self, query_tokens: list[str]) -> list[int]:
        scores = [self._score(query_tokens, i) for i in range(self.n_docs)]
        return sorted(range(self.n_docs), key=lambda i: -scores[i])

    def _score(self, query_tokens: list[str], i: int) -> float:
        tf = self.tfs[i]
        dl = len(self.corpus[i])
        total = 0.0
        for token in query_tokens:
            f = tf.get(token, 0)
            if not f or token not in self.idf:
                continue
            total += (
                self.idf[token]
                * (f * (self.k1 + 1))
                / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            )
        return total


def _read_asc(path: Path, encoding: str) -> list[list[str]]:
    """Rows of a '$'-delimited MedDRA distribution file, as positional fields.

    MSSO's files end each line with a trailing '$' and JMO's *_j.asc files do not;
    reading fields by position makes the difference irrelevant.
    """
    with path.open(encoding=encoding) as f:
        return [line.rstrip("\r\n").split("$") for line in f if line.strip()]


def load_meddra_ascii(directory: Path) -> list[MeddraTerm]:
    """PTs from a licensed MedDRA/J ASCII distribution folder (bring your own).

    Field order follows the MedDRA and MedDRA/J Distribution File Format
    documents (v27.0):

    - pt.asc     pt_code $ pt_name $ ...            (extended ASCII; required)
    - pt_j.asc   pt_code $ pt_kanji $ pt_kana ...   (Shift-JIS; required)
    - mdhier.asc pt_code $ hlt_code $ hlgt_code $ soc_code $ pt_name $ hlt_name $
                 hlgt_name $ soc_name $ soc_abbrev $ null_field $ pt_soc_code $
                 primary_soc_fg                     (optional: primary SOC per PT)
    - soc_j.asc  soc_code $ soc_kanji $ ...         (Shift-JIS; optional)

    The SOC shown is the PT's primary SOC, in Japanese when soc_j.asc is present.
    """
    pt_file, pt_j_file = directory / "pt.asc", directory / "pt_j.asc"
    for required in (pt_file, pt_j_file):
        if not required.exists():
            raise FileNotFoundError(f"MedDRA ASCII file not found: {required}")

    kanji = {r[0]: r[1] for r in _read_asc(pt_j_file, "cp932")}

    primary_soc: dict[str, tuple[str, str]] = {}  # pt_code -> (soc_code, soc_name)
    if (directory / "mdhier.asc").exists():
        for r in _read_asc(directory / "mdhier.asc", "latin-1"):
            if r[11] == "Y":
                primary_soc[r[0]] = (r[3], r[7])
    soc_kanji: dict[str, str] = {}
    if (directory / "soc_j.asc").exists():
        soc_kanji = {r[0]: r[1] for r in _read_asc(directory / "soc_j.asc", "cp932")}

    terms: list[MeddraTerm] = []
    for r in _read_asc(pt_file, "latin-1"):
        code, name_en = r[0], r[1]
        soc_code, soc_en = primary_soc.get(code, ("", ""))
        terms.append(
            MeddraTerm(
                pt_code=code,
                pt_name_ja=kanji.get(code) or name_en,
                pt_name_en=name_en,
                soc_name_ja=soc_kanji.get(soc_code) or soc_en or None,
            )
        )
    return terms


class MeddraDictionary:
    """Load the PT dictionary and provide the lexical ranking signals.

    ``path`` is either a CSV (the bundled fictional demo terminology, or any file
    with the same columns) or a folder holding a licensed MedDRA/J ASCII
    distribution — see ``load_meddra_ascii``. MedDRA itself is not bundled.
    """

    def __init__(self, path: str) -> None:
        p = Path(path)
        self.terms = load_meddra_ascii(p) if p.is_dir() else self._load(p)
        self._bm25 = _BM25([char_bigrams(t.pt_name_ja) for t in self.terms])

    def _load(self, path: Path) -> list[MeddraTerm]:
        if not path.exists():
            raise FileNotFoundError(f"PT dictionary not found: {path}")
        terms: list[MeddraTerm] = []
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                terms.append(
                    MeddraTerm(
                        pt_code=row["pt_code"],
                        pt_name_ja=row["pt_name_ja"],
                        pt_name_en=(row.get("pt_name_en") or None),
                        soc_name_ja=(row.get("soc_name_ja") or None),
                    )
                )
        return terms

    def exact_matches(self, term: str) -> list[int]:
        """Indices whose PT name (ja or en) equals the term after normalization."""
        q = normalize(term)
        return [
            i
            for i, t in enumerate(self.terms)
            if normalize(t.pt_name_ja) == q
            or (t.pt_name_en and normalize(t.pt_name_en) == q)
        ]

    def bm25_rank(self, term: str) -> list[int]:
        """All PT indices ranked best-first by char-bigram BM25 against the term."""
        return self._bm25.rank(char_bigrams(term))
