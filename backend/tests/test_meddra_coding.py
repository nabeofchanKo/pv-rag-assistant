"""Unit tests for MeddraCodingService (no LLM / no vector store — fakes only).

Pins the coding policy: a single exact match codes deterministically without the
LLM; otherwise the LLM must pick a *presented* candidate's pt_code, and anything
else (null / unknown code / no candidates) falls back to 該当なし.
"""

from app.schemas import MeddraTerm
from app.services.meddra_coding import MeddraCodingService, _Selection


def _pt(code, ja, soc="SOC"):
    return MeddraTerm(pt_code=code, pt_name_ja=ja, soc_name_ja=soc)


class FakeRetriever:
    def __init__(self, exact=None, search=None):
        self.exact = exact or {}
        self.search_map = search or {}

    def exact_matches(self, term):
        return self.exact.get(term, [])

    def search(self, term, top_k=5):
        return self.search_map.get(term, [])


class FakeChain:
    def __init__(self, by_term):
        self.by_term = by_term
        self.calls = 0

    def invoke(self, inputs):
        self.calls += 1
        return self.by_term[inputs["term"]]


def _service(retriever, chain):
    svc = MeddraCodingService.__new__(MeddraCodingService)
    svc.retriever = retriever
    svc.top_k = 5
    svc.chain = chain
    return svc


def test_single_exact_match_codes_deterministically_without_llm():
    retriever = FakeRetriever(exact={"頭痛": [_pt("10019211", "頭痛")]})
    chain = FakeChain({})
    svc = _service(retriever, chain)

    c = svc.code(["頭痛"])[0]

    assert c.coded_by == "完全一致"
    assert (c.pt_code, c.pt_name_ja) == ("10019211", "頭痛")
    assert chain.calls == 0  # no LLM for an exact hit


def test_llm_selects_a_presented_candidate():
    cands = [_pt("10024690", "肝障害"), _pt("10072268", "薬物性肝障害")]
    retriever = FakeRetriever(search={"薬剤性肝障害": cands})
    chain = FakeChain({"薬剤性肝障害": _Selection(pt_code="10072268", rationale="変種の同義")})
    svc = _service(retriever, chain)

    c = svc.code(["薬剤性肝障害"])[0]

    assert c.coded_by == "検索+LLM"
    assert c.pt_name_ja == "薬物性肝障害"
    assert len(c.candidates) == 2


def test_llm_code_outside_candidates_falls_back_to_none():
    retriever = FakeRetriever(search={"謎の事象": [_pt("10019211", "頭痛")]})
    chain = FakeChain({"謎の事象": _Selection(pt_code="99999999")})  # not a candidate
    svc = _service(retriever, chain)

    c = svc.code(["謎の事象"])[0]

    assert c.coded_by == "該当なし"
    assert c.pt_code is None
    assert len(c.candidates) == 1  # candidates preserved for audit


def test_no_candidates_is_none_without_llm():
    retriever = FakeRetriever()  # no exact, no search results
    chain = FakeChain({})
    svc = _service(retriever, chain)

    c = svc.code(["存在しない"])[0]

    assert c.coded_by == "該当なし"
    assert chain.calls == 0
