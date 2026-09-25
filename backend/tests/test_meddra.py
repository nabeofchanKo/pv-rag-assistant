"""Unit tests for the MedDRA lexical ranking (ADR 0003, Level B sparse half).

Loads the real dictionary directly by path (no settings / no API). Pins the
properties that motivated the hybrid choice: exact match works, and char-bigram
BM25 ranks the correct morphological variant above a shorter partial.
"""

from pathlib import Path

from app.services.meddra import MeddraDictionary, char_bigrams, rrf_fuse

CSV = (
    Path(__file__).resolve().parents[2] / "data" / "meddra_sample" / "meddra_pt.csv"
)


def _dic() -> MeddraDictionary:
    return MeddraDictionary(str(CSV))


def _names(dic, ranking):
    return [dic.terms[i].pt_name_ja for i in ranking]


def test_dictionary_loads():
    dic = _dic()
    assert len(dic.terms) > 40
    assert any(t.pt_name_ja == "頭痛" and t.pt_code == "10019211" for t in dic.terms)


def test_exact_match_ja_and_en():
    dic = _dic()
    assert _names(dic, dic.exact_matches("頭痛")) == ["頭痛"]
    # English name, case-insensitive
    assert dic.terms[dic.exact_matches("headache")[0]].pt_name_ja == "頭痛"
    assert dic.exact_matches("存在しない有害事象XYZ") == []


def test_bm25_ranks_correct_variant_above_shorter_partial():
    dic = _dic()
    # 薬剤性肝障害 -> 薬物性肝障害 should beat the shorter 肝障害 (the Level A failure)
    names = _names(dic, dic.bm25_rank("薬剤性肝障害"))
    assert names.index("薬物性肝障害") < names.index("肝障害")


def test_bm25_prefers_morphological_variant_over_generic():
    dic = _dic()
    # 肝機能障害 -> 肝機能異常 should beat 肝障害 (vector/Level A ranked 肝障害 first)
    names = _names(dic, dic.bm25_rank("肝機能障害"))
    assert names.index("肝機能異常") < names.index("肝障害")


def test_char_bigrams():
    assert char_bigrams("徐脈") == ["徐", "脈", "徐脈"]


def test_rrf_prefers_items_ranked_high_in_both():
    # index 5 is #1 in both rankings -> must win
    assert rrf_fuse([[5, 0, 1], [5, 2, 3]])[0] == 5
    # index 1 appears in both; index 0 and 2 only once -> 1 should lead
    assert rrf_fuse([[0, 1], [2, 1]])[0] == 1
