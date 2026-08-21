"""Phase 3: expectedness (既知/未知) assessment via RAG over the drug label.

For each adverse event, retrieve the most relevant passages of the *suspect
drug's* package insert (添付文書) and classify how the event matches the label.
This is judgment — kept separate from the faithful extraction step.

Confidence gate (deterministic policy over an LLM classification):
  the LLM only classifies the *type* of match (direct / synonym / loose / mechanism
  / none) + cites the passage; **this service** maps match type -> verdict. Only
  a confident match (直接一致 / 同義語) becomes 既知. A loose match (読み替え・類似)
  or a mechanism-only mention (機序・文脈のみ) becomes 要確認 — treated as *not
  expected* downstream (safe side) but carrying the possible-known passage for a
  human to confirm. The worst case for a first-pass screen is over-reading 既知 and
  burying a genuinely unexpected, serious event with a short reporting deadline;
  the gate biases against that. ``ExpectednessAssessment.is_expected`` is True only
  for 既知, so 要確認 / 未知 never suppress expedited-reporting logic.

Design note: this is "Approach A" (per-event retrieval). A future "Approach C"
(read the label once into a structured, cited ADR list, then match) is recorded
in the README for later A/B comparison. The 要確認 layer is also the hook the
planned MedDRA-PT comparison will feed into (only mark 既知 when term AND PT agree).
"""

import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.schemas import Chunk, DrugExpectedness, ExpectednessAssessment
from app.services.retriever import RetrieverService

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（PV）の担当者です。ある被疑薬の添付文書から検索した抜粋"
    "（コンテキスト）だけを根拠に、指定された有害事象がその添付文書にどの程度該当するかを、"
    "次の match_type から1つ選んで分類してください。既知／未知の最終判定は当方のポリシーで"
    "決めるので、あなたは『一致の種類の分類』と『根拠の抜き出し』に専念してください。\n"
    "match_type:\n"
    "・直接一致: 有害事象と同じ語（または同語を含む記載）がある。例: 「頭痛」に対し副作用欄「頭痛」。\n"
    "・同義語: 明らかな医学的同義。例: 肝機能異常≒肝機能障害、悪心≒吐き気、薬物性肝障害≒肝機能障害。\n"
    "・読み替え・類似: 同じ大分類だが別事象、または総称↔特定の読み替え（完全同一とは言い切れない）。"
    "例: 回転性めまい↔浮動性めまい（別サブタイプ）、浮腫↔血管浮腫／末梢性浮腫（総称↔特定）。\n"
    "・機序・文脈のみ: 独立した副作用として列挙されておらず、機序や注意喚起の文脈でのみ言及。"
    "例: 「血圧低下」が「過度の血圧低下に伴い失神」等の文脈にだけ登場。\n"
    "・該当なし: コンテキストのどこにも関連記載がない。\n"
    "ルール:\n"
    "・コンテキストに無い情報を一般知識で補わない。少しでも該当し得る記載があれば該当する種類を選び、"
    "その原文を evidence_quote に引用し、可能なら項目名（例: 11.1 重大な副作用、10. 相互作用）を "
    "evidence_section に記す。\n"
    "・迷ったら強い方（直接一致・同義語）に寄せないこと。サブタイプ違い・総称・機序の言及は、"
    "必ず読み替え・類似／機序・文脈のみ の側に分類する（安全側）。\n"
    "・該当なしのときは evidence を空にする。\n"
    "・rationale は日本語で簡潔に。"
)


# Deterministic policy: which match types become which verdict. Only confident
# matches are 既知; loose / mechanism matches are 要確認 (surfaced for HITL, but
# counted as *not expected*). Edit this table to tune strictness.
_MATCH_TYPE_TO_VERDICT: dict[str, str] = {
    "直接一致": "既知",
    "同義語": "既知",
    "読み替え・類似": "要確認",
    "機序・文脈のみ": "要確認",
    "該当なし": "未知",
}

# Canonical rationales so non-既知 verdicts read uniformly (the LLM's free-text
# reasons vary run to run). 既知 / 要確認 keep the cited evidence passage.
_REVIEW_RATIONALE = (
    "この記載から既知の可能性がありますが、一致が確実でないため安全側で未知として評価します"
    "（人手確認が必要）。"
)
_UNKNOWN_RATIONALE = "添付文書（副作用・相互作用の各欄）に本事象に該当する記載は見つかりませんでした。"
_UNDETERMINED_RATIONALE = "提示された添付文書の抜粋だけでは、記載の有無を判断できませんでした。"
_NO_LABEL_RATIONALE = "該当薬剤の添付文書から参照箇所を取得できませんでした。"


class _Judgment(BaseModel):
    """Structured output: the LLM classifies the match type + cites evidence.
    The verdict itself is derived by policy (not asked of the LLM)."""

    match_type: Literal[
        "直接一致", "同義語", "読み替え・類似", "機序・文脈のみ", "該当なし"
    ] = Field(description="有害事象と添付文書の記載との一致の種類。")
    rationale: str | None = Field(default=None, description="分類理由を日本語で簡潔に。")
    evidence_quote: str | None = Field(
        default=None, description="根拠とした添付文書の該当箇所（原文引用）。該当ありなら記載。"
    )
    evidence_section: str | None = Field(
        default=None, description='該当項目名（例: "11.1 重大な副作用" / "10. 相互作用"）。'
    )


class ExpectednessService:
    """Assess expectedness of adverse events against a drug's package insert."""

    def __init__(
        self, llm: BaseChatModel, retriever: RetrieverService, top_k: int = 4
    ) -> None:
        self.retriever = retriever
        self.top_k = top_k
        self.chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    (
                        "human",
                        "被疑薬: {drug_name}\n判定対象の有害事象: {term}\n\n"
                        "添付文書の抜粋（コンテキスト）:\n{context}",
                    ),
                ]
            )
            | llm.with_structured_output(_Judgment)
        )

    def assess(
        self, drug_name: str, label_document: str, terms: list[str]
    ) -> DrugExpectedness:
        """Assess every term against ``label_document`` (one adverse event at a time)."""

        assessments = [
            self._assess_term(drug_name, label_document, term) for term in terms
        ]
        return DrugExpectedness(
            drug_name=drug_name,
            label_document=label_document,
            assessments=assessments,
        )

    def _assess_term(
        self, drug_name: str, label_document: str, term: str
    ) -> ExpectednessAssessment:
        # Scope the search to this drug's insert only.
        chunks = self.retriever.search(
            term, top_k=self.top_k, filter={"document_name": label_document}
        )
        if not chunks:
            # Label not indexed / no passages — cannot ground a judgment.
            return ExpectednessAssessment(
                term=term, verdict="判定不能", rationale=_NO_LABEL_RATIONALE
            )

        judgment: _Judgment = self.chain.invoke(
            {
                "drug_name": drug_name,
                "term": term,
                "context": self._build_context(chunks),
            }
        )
        return self._finalize(term, judgment)

    @staticmethod
    def _finalize(term: str, judgment: _Judgment) -> ExpectednessAssessment:
        """Map the LLM's match_type to a verdict via policy. 既知 / 要確認 keep the
        cited evidence; 未知 / 判定不能 get a canonical rationale and no evidence."""
        verdict = _MATCH_TYPE_TO_VERDICT.get(judgment.match_type, "判定不能")

        if verdict == "既知":
            return ExpectednessAssessment(
                term=term,
                verdict="既知",
                match_type=judgment.match_type,
                rationale=judgment.rationale,
                evidence_quote=judgment.evidence_quote,
                evidence_section=judgment.evidence_section,
            )
        if verdict == "要確認":
            # Keep the possible-known passage so a human can confirm 既知 vs 未知.
            return ExpectednessAssessment(
                term=term,
                verdict="要確認",
                match_type=judgment.match_type,
                rationale=_REVIEW_RATIONALE,
                evidence_quote=judgment.evidence_quote,
                evidence_section=judgment.evidence_section,
            )
        if verdict == "未知":
            return ExpectednessAssessment(
                term=term,
                verdict="未知",
                match_type=judgment.match_type,
                rationale=_UNKNOWN_RATIONALE,
            )
        return ExpectednessAssessment(
            term=term, verdict="判定不能", rationale=_UNDETERMINED_RATIONALE
        )

    def _build_context(self, chunks: list[Chunk]) -> str:
        parts = [
            f"[抜粋 {i}: {c.document_name}]\n{c.text}"
            for i, c in enumerate(chunks, start=1)
        ]
        return "\n\n".join(parts)
