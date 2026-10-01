"""Unit tests for the MedDRA lexical ranking (ADR 0003, Level B sparse half).

Loads the bundled demo dictionary directly by path (no settings / no API). Pins the
properties that motivated the hybrid choice: exact match works, and char-bigram
BM25 ranks the correct morphological variant above a shorter partial.
"""

from pathlib import Path

from app.services.meddra import MeddraDictionary, char_bigrams, rrf_fuse

CSV = (
    Path(__file__).resolve().parents[2] / "data" / "terminology" / "demo_pt.csv"
)


def _dic() -> MeddraDictionary:
    return MeddraDictionary(str(CSV))


def _names(dic, ranking):
    return [dic.terms[i].pt_name_ja for i in ranking]


def test_dictionary_loads():
    dic = _dic()
    assert len(dic.terms) > 40
    assert any(t.pt_name_ja == "頭痛" and t.pt_code == "DEMO-0001" for t in dic.terms)


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


# --- Bring-your-own MedDRA: the licensed ASCII distribution (ADR 0014) ---
# The files below are hand-made in the documented layout with fictional codes and
# names; no MedDRA content is used. MSSO files end each line with "$", JMO's
# *_j.asc do not and are Shift-JIS.


def _write_ascii_distribution(folder: Path) -> None:
    (folder / "pt.asc").write_text(
        "90000001$Demo headache$$90000100$$$$$$$$\n"
        "90000002$Demo rash$$90000200$$$$$$$$\n",
        encoding="latin-1",
    )
    (folder / "pt_j.asc").write_text(
        "90000001$デモ頭痛$でもずつう$$\n90000002$デモ発疹$でもほっしん$$\n",
        encoding="cp932",
    )
    # PT 90000002 sits under two SOCs; only the primary one (flag Y) is kept.
    (folder / "mdhier.asc").write_text(
        "90000001$1$2$90000100$Demo headache$h$g$Demo nervous$DNS$$90000100$Y$\n"
        "90000002$3$4$90000300$Demo rash$h$g$Demo immune$DIM$$90000200$N$\n"
        "90000002$5$6$90000200$Demo rash$h$g$Demo skin$DSK$$90000200$Y$\n",
        encoding="latin-1",
    )
    (folder / "soc_j.asc").write_text("90000100$デモ神経系$1$$$\n", encoding="cp932")


def test_ascii_distribution_loads_names_and_primary_soc(tmp_path):
    _write_ascii_distribution(tmp_path)
    dic = MeddraDictionary(str(tmp_path))
    by_code = {t.pt_code: t for t in dic.terms}

    assert by_code["90000001"].pt_name_ja == "デモ頭痛"
    assert by_code["90000001"].pt_name_en == "Demo headache"
    assert by_code["90000001"].soc_name_ja == "デモ神経系"  # Japanese SOC from soc_j.asc
    assert by_code["90000002"].soc_name_ja == "Demo skin"  # primary SOC; no Japanese name
    assert _names(dic, dic.exact_matches("デモ頭痛")) == ["デモ頭痛"]


def test_ascii_distribution_requires_japanese_names(tmp_path):
    _write_ascii_distribution(tmp_path)
    (tmp_path / "pt_j.asc").unlink()
    try:
        MeddraDictionary(str(tmp_path))
    except FileNotFoundError as e:
        assert "pt_j.asc" in str(e)
    else:
        raise AssertionError("missing pt_j.asc must fail loudly")


def test_index_is_rebuilt_when_the_dictionary_changes(tmp_path):
    """Swapping the demo terminology for MedDRA must not leave a stale vector index."""
    from langchain_core.embeddings import DeterministicFakeEmbedding

    from app.services.meddra_retriever import HybridMeddraRetriever

    def retriever(dic):
        return HybridMeddraRetriever(
            dic, DeterministicFakeEmbedding(size=8), persist_dir=str(tmp_path / "chroma")
        )

    demo = _dic()
    assert retriever(demo).ensure_indexed() == len(demo.terms)
    assert retriever(demo).ensure_indexed() == 0  # unchanged -> skipped

    folder = tmp_path / "meddra"
    folder.mkdir()
    _write_ascii_distribution(folder)
    swapped = retriever(MeddraDictionary(str(folder)))
    assert swapped.ensure_indexed() == 2
    assert set(swapped.store.get(include=[])["ids"]) == {"90000001", "90000002"}
