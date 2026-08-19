"""Phase 2 (slice 1): extract structured patient + adverse-event data from case text.

Uses the LLM's structured-output mode to fill a Pydantic schema. Extraction is
faithful ("as reported") and makes no clinical judgments — seriousness, causality,
expectedness, and MedDRA coding are later phases.

Drug extraction is intentionally out of scope here: drug wording varies widely by
reporter and touches sensitive off-label questions, so drug identification will be
handled later as controlled matching against a company product master rather than
free-text extraction.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.schemas import CaseExtraction

logger = logging.getLogger(__name__)


EXTRACTION_SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（PV）の担当者です。与えられた症例テキストから、"
    "患者情報と有害事象を抽出してください。\n"
    "\n"
    "【有害事象の抽出は必ず2段階で行うこと】\n"
    "1. まず「有害事象」欄などに明記された事象を抽出し、source を \"reported\" とする。\n"
    "2. 次に、経過（ナラティブ）を最初から丁寧に読み直し、そこに記述されているが上記リストに"
    "無い有害事象を追加し、source を \"narrative\" とする。対象には症状・随伴事象・検査値異常・"
    "転倒などの臨床的に有害な所見を含める。\n"
    "   例：「本剤投与後にめまいが出現し転倒した」→ めまい と 転倒（いずれも narrative）。\n"
    "   例：「QTc が 498 ms に延長した」→ QT延長（narrative）。\n"
    "\n"
    "【厳守事項】\n"
    "・記載されている内容のみを、原文の表現のまま抽出する（正規化・言い換え・解釈をしない）。\n"
    "・同じ事象を reported と narrative の両方に重複して挙げない。\n"
    "・記載のない項目は省略する（推測して埋めない）。\n"
    "・重篤度・因果関係などの判定は行わない。報告書にそう書かれている場合のみ、その記載を転記する。"
)


class ExtractionService:
    """Extract a structured CaseExtraction from free-form case text."""

    def __init__(self, llm: BaseChatModel) -> None:
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EXTRACTION_SYSTEM_PROMPT),
                ("human", "症例テキスト:\n\n{case_text}"),
            ]
        )
        # with_structured_output constrains the model to emit a valid CaseExtraction.
        self.chain = self.prompt | llm.with_structured_output(CaseExtraction)

    def extract(self, case_text: str) -> CaseExtraction:
        return self.chain.invoke({"case_text": case_text})
