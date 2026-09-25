"""Unit tests for ExpectednessService (no LLM / no vector store — fakes only).

These pin the service's orchestration + policy: search is scoped to the drug's
own label, the input term is preserved, the LLM's match_type is mapped to a
verdict by deterministic policy (only 直接一致/同義語 -> 既知; loose/mechanism ->
要確認, kept as *not expected*), and a missing label yields 判定不能 without an LLM
call.
"""

from datetime import datetime, timezone

from app.schemas import Chunk
from app.services.expectedness import (
    _REVIEW_RATIONALE,
    _UNKNOWN_RATIONALE,
    ExpectednessService,
    _Judgment,
)


def _chunk(text: str, document_name: str = "drugx_label.md") -> Chunk:
    return Chunk(
        document_name=document_name,
        chunk_index=0,
        page_number=1,
        total_chunks=1,
        char_start=0,
        char_end=len(text),
        text=text,
        created_at=datetime.now(timezone.utc),
    )


class FakeRetriever:
    """Records search calls and returns canned chunks per query term."""

    def __init__(self, results_by_term: dict[str, list[Chunk]]):
        self.results_by_term = results_by_term
        self.calls: list[dict] = []

    def search(self, query, top_k=3, filter=None):
        self.calls.append({"query": query, "top_k": top_k, "filter": filter})
        return self.results_by_term.get(query, [])


class FakeChain:
    """Stand-in for the LCEL classification chain: term -> canned _Judgment."""

    def __init__(self, judgments_by_term: dict[str, _Judgment]):
        self.judgments_by_term = judgments_by_term
        self.invoked_terms: list[str] = []

    def invoke(self, inputs):
        term = inputs["term"]
        self.invoked_terms.append(term)
        return self.judgments_by_term[term]


def _service(retriever, chain, top_k=4):
    svc = ExpectednessService.__new__(ExpectednessService)  # skip __init__ (builds real chain)
    svc.retriever = retriever
    svc.top_k = top_k
    svc.chain = chain
    return svc


def test_search_is_scoped_to_the_drug_label():
    retriever = FakeRetriever({"頭痛": [_chunk("その他の副作用: 頭痛")]})
    chain = FakeChain({"頭痛": _Judgment(match_type="直接一致", evidence_quote="頭痛")})
    svc = _service(retriever, chain, top_k=4)

    svc.assess("DrugX", "drugx_label.md", ["頭痛"])

    assert retriever.calls[0]["filter"] == {"document_name": "drugx_label.md"}
    assert retriever.calls[0]["top_k"] == 4


def test_match_type_maps_to_verdict_by_policy():
    retriever = FakeRetriever(
        {"頭痛": [_chunk("x")], "回転性めまい": [_chunk("x")], "発疹": [_chunk("x")]}
    )
    chain = FakeChain(
        {
            "頭痛": _Judgment(match_type="直接一致", evidence_quote="頭痛"),
            "回転性めまい": _Judgment(match_type="読み替え・類似", evidence_quote="浮動性めまい"),
            "発疹": _Judgment(match_type="該当なし"),
        }
    )
    svc = _service(retriever, chain)

    result = svc.assess("DrugX", "drugx_label.md", ["頭痛", "回転性めまい", "発疹"])
    verdicts = {a.term: a.verdict for a in result.assessments}

    assert verdicts == {"頭痛": "既知", "回転性めまい": "要確認", "発疹": "未知"}
    assert [a.term for a in result.assessments] == ["頭痛", "回転性めまい", "発疹"]


def test_review_keeps_evidence_but_is_not_expected():
    # 要確認 must surface the possible-known passage yet count as NOT expected.
    retriever = FakeRetriever({"血圧低下": [_chunk("過度の血圧低下に伴い失神")]})
    chain = FakeChain(
        {
            "血圧低下": _Judgment(
                match_type="機序・文脈のみ",
                evidence_quote="過度の血圧低下に伴い失神",
                evidence_section="8. 重要な基本的注意",
            )
        }
    )
    svc = _service(retriever, chain)

    a = svc.assess("DrugX", "drugx_label.md", ["血圧低下"]).assessments[0]

    assert a.verdict == "要確認"
    assert a.is_expected is False  # the whole point: does not suppress reporting
    assert a.evidence_quote == "過度の血圧低下に伴い失神"
    assert a.evidence_section == "8. 重要な基本的注意"
    assert a.rationale == _REVIEW_RATIONALE


def test_known_is_expected_and_keeps_evidence():
    retriever = FakeRetriever({"頭痛": [_chunk("11.2 その他の副作用: 頭痛")]})
    chain = FakeChain(
        {"頭痛": _Judgment(match_type="直接一致", evidence_quote="頭痛", evidence_section="11.2 その他の副作用")}
    )
    svc = _service(retriever, chain)

    a = svc.assess("DrugX", "drugx_label.md", ["頭痛"]).assessments[0]

    assert a.verdict == "既知"
    assert a.is_expected is True
    assert a.evidence_quote == "頭痛"


def test_none_match_is_unknown_with_canonical_rationale_and_no_evidence():
    # Even if the LLM leaks a stray quote on 該当なし, the service clears it.
    retriever = FakeRetriever({"発疹": [_chunk("その他の副作用: 頭痛")]})
    chain = FakeChain({"発疹": _Judgment(match_type="該当なし", evidence_quote="頭痛")})
    svc = _service(retriever, chain)

    a = svc.assess("DrugX", "drugx_label.md", ["発疹"]).assessments[0]

    assert a.verdict == "未知"
    assert a.rationale == _UNKNOWN_RATIONALE
    assert a.evidence_quote is None
    assert a.evidence_section is None


def test_missing_label_is_undetermined_without_calling_llm():
    retriever = FakeRetriever({})  # no chunks for any term
    chain = FakeChain({})  # would KeyError if invoked
    svc = _service(retriever, chain)

    a = svc.assess("DrugX", "drugx_label.md", ["頭痛"]).assessments[0]

    assert a.verdict == "判定不能"
    assert a.is_expected is False
    assert chain.invoked_terms == []  # LLM not called when there is nothing to ground on
