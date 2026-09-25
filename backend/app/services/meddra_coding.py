"""MedDRA PT coding: suggest a Preferred Term for each adverse-event term.

A single normalized exact match is coded **deterministically** (no LLM) — fast and
auditable. Otherwise the fused hybrid candidates (ADR 0003) are handed to an LLM
that must pick one candidate's ``pt_code`` or return none (該当なし). The LLM is
constrained to the presented candidates so it cannot invent codes.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.schemas import MeddraCoding, MeddraTerm
from app.services.meddra_retriever import HybridMeddraRetriever

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "あなたはMedDRAコーディングの担当者です。与えられた有害事象の用語に最も適合する "
    "MedDRA基本語（PT）を、提示された候補リストの中から1つだけ選んでください。\n"
    "・必ず候補の中から選び、候補の pt_code をそのまま返すこと（候補外のコードは使わない）。\n"
    "・医学的に適合する候補が無い場合は pt_code を空（null）にすること（無理に当てはめない）。\n"
    "・回転性めまいと浮動性めまいのような明確に異なる病態は、安易に同一視しないこと。\n"
    "・rationale は日本語で簡潔に。"
)


class _Selection(BaseModel):
    """LLM output: the chosen candidate's pt_code (or null for 該当なし)."""

    pt_code: str | None = Field(
        default=None, description="選んだ候補の pt_code。適合が無ければ null。"
    )
    rationale: str | None = Field(default=None, description="選択理由を日本語で簡潔に。")


class MeddraCodingService:
    """Suggest a MedDRA PT for each adverse-event term (hybrid retrieval + LLM select)."""

    def __init__(
        self, llm: BaseChatModel, retriever: HybridMeddraRetriever, top_k: int = 5
    ) -> None:
        self.retriever = retriever
        self.top_k = top_k
        self.chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    ("human", "有害事象: {term}\n\n候補:\n{candidates}"),
                ]
            )
            | llm.with_structured_output(_Selection)
        )

    def code(self, terms: list[str]) -> list[MeddraCoding]:
        return [self._code_term(t) for t in terms]

    def _code_term(self, term: str) -> MeddraCoding:
        # Deterministic fast path: a single exact dictionary match.
        exact = self.retriever.exact_matches(term)
        if len(exact) == 1:
            return self._coding(term, exact[0], "完全一致", "辞書のPT名と完全一致。", exact)

        candidates = self.retriever.search(term, self.top_k)
        if not candidates:
            return MeddraCoding(term=term, coded_by="該当なし", rationale="候補が得られませんでした。")

        selection: _Selection = self.chain.invoke(
            {"term": term, "candidates": self._render(candidates)}
        )
        chosen = next((c for c in candidates if c.pt_code == selection.pt_code), None)
        if chosen is None:
            return MeddraCoding(
                term=term,
                coded_by="該当なし",
                rationale=selection.rationale or "適合する候補がありませんでした。",
                candidates=candidates,
            )
        return self._coding(term, chosen, "検索+LLM", selection.rationale, candidates)

    @staticmethod
    def _coding(
        term: str,
        pt: MeddraTerm,
        coded_by: str,
        rationale: str | None,
        candidates: list[MeddraTerm],
    ) -> MeddraCoding:
        return MeddraCoding(
            term=term,
            pt_code=pt.pt_code,
            pt_name_ja=pt.pt_name_ja,
            soc_name_ja=pt.soc_name_ja,
            coded_by=coded_by,
            rationale=rationale,
            candidates=candidates,
        )

    @staticmethod
    def _render(candidates: list[MeddraTerm]) -> str:
        return "\n".join(
            f"- pt_code={c.pt_code} / {c.pt_name_ja}（{c.soc_name_ja or ''}）"
            for c in candidates
        )
