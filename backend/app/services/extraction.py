"""Phase 2: structured extraction of patient + adverse events from case text.

Adverse-event extraction is a **two-call decomposition** to reliably avoid
duplicates:
  1. extract the *reported* events (from the structured "有害事象" section) + patient,
  2. pass that reported list back to the model and extract only the *new* events
     described in the narrative that are not already in the reported list.

A single call that tries to do both at once re-lists narrative rephrasings of
reported events as if they were new (observed repeatedly with both gpt-4o-mini
and gpt-4o), so the reported list is made explicit to the second call instead of
relying on the model to de-duplicate implicitly.

Extraction is faithful ("as reported") and makes no clinical judgments. Drug
extraction is intentionally out of scope (handled by product-master matching).
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.schemas import AdverseEventCore, AdverseEventMention, CaseExtraction, Patient

logger = logging.getLogger(__name__)


REPORTED_SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（PV）の担当者です。症例テキストから、患者情報と、"
    "「有害事象」欄などに明記された有害事象のみを抽出してください。\n"
    "・この段階では、経過（ナラティブ）にしか書かれていない事象は拾わない（後段で扱う）。\n"
    "・事象名は報告書の記載どおりに転記し、部位・性状・程度・経過などの修飾語も"
    "省略しない（例：「そう痒症（全身性）」「鼻出血（反復性）」「頭痛（重度）」"
    "「徐脈（症候性）」）。ただし併記された英語のMedDRA英名（例：（Pruritus））は"
    "コード化で扱うため事象名には含めない。\n"
    "・各事象について、発現日・転帰・報告上の重篤度を記載どおりに転記する（無ければ省略）。\n"
    "・患者の年齢・性別を抽出する。\n"
    "・重篤度・因果関係などの判定は行わない（記載があれば転記のみ）。"
)

NARRATIVE_SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（PV）の担当者です。以下は、ある症例について既に抽出済みの"
    "『報告済み有害事象』の一覧です。\n\n"
    "{reported_terms}\n\n"
    "症例テキストの経過（ナラティブ）を最初から丁寧に読み、上記一覧に【含まれていない"
    "新規の有害事象のみ】を抽出してください。\n"
    "・経過が上記の事象を言い換え・詳述しているだけの場合は新規ではない（含めない）。"
    "例：「拍動性の前頭部頭痛」は「頭痛」と同一、「起立時のめまい」は「めまい」と同一、"
    "「軽度の起立性低血圧」は「起立性低血圧」と同一。\n"
    "・新規に該当するのは、報告欄に無い症状・随伴事象・検査値異常・転倒などの有害な所見"
    "（例：QT延長、転倒）。\n"
    "・各事象の発現日・転帰は記載どおりに転記する（無ければ省略）。\n"
    "・報告重篤度は、報告書がその事象について明示している場合のみ転記する。経過から読み取った"
    "事象は通常その明示が無いため省略（null）とし、周辺の他事象の重篤度を流用・推測しない"
    "（例：同日に重篤な徐脈・失神があっても、QT延長の報告重篤度は空欄のまま）。\n"
    "・実際に発現した事象のみを対象とする。否定・不在の記述から事象を作らない"
    "（例：「嘔吐を伴わない悪心」→ 悪心はありだが嘔吐は無いので、嘔吐は含めない）。\n"
    "・本文に明記されていない事象を推測・追加しない"
    "（例：失神の記述だけから「転倒」を推測しない）。\n"
    "・新規の事象が無ければ空のリストを返す。\n"
    "・記載どおりの表現で抽出し、正規化・解釈はしない。"
)


class _ReportedCase(BaseModel):
    """Structured output for call 1 (patient + reported adverse events)."""

    patient: Patient
    adverse_events: list[AdverseEventCore]


class _NarrativeEvents(BaseModel):
    """Structured output for call 2 (narrative-only new adverse events)."""

    adverse_events: list[AdverseEventCore]


class ExtractionService:
    """Extract a CaseExtraction via a two-call (reported -> narrative) decomposition."""

    def __init__(self, reported_llm: BaseChatModel, narrative_llm: BaseChatModel) -> None:
        # The reported-events call is a simple structured extraction (mini is enough).
        # The narrative-diff call is the hard semantic step (de-dupe rephrasings,
        # respect negation, do not infer) and uses a stronger model.
        self.reported_chain = (
            ChatPromptTemplate.from_messages(
                [("system", REPORTED_SYSTEM_PROMPT), ("human", "症例テキスト:\n\n{case_text}")]
            )
            | reported_llm.with_structured_output(_ReportedCase)
        )
        self.narrative_chain = (
            ChatPromptTemplate.from_messages(
                [("system", NARRATIVE_SYSTEM_PROMPT), ("human", "症例テキスト:\n\n{case_text}")]
            )
            | narrative_llm.with_structured_output(_NarrativeEvents)
        )

    def extract(self, case_text: str) -> CaseExtraction:
        # Call 1: reported events + patient.
        reported = self.reported_chain.invoke({"case_text": case_text})

        # Call 2: only narrative events NOT already in the reported list.
        reported_terms = (
            "\n".join(f"・{ae.term}" for ae in reported.adverse_events)
            or "（報告済み有害事象なし）"
        )
        narrative = self.narrative_chain.invoke(
            {"case_text": case_text, "reported_terms": reported_terms}
        )

        adverse_events = [
            AdverseEventMention(source="reported", **ae.model_dump())
            for ae in reported.adverse_events
        ] + [
            AdverseEventMention(source="narrative", **ae.model_dump())
            for ae in narrative.adverse_events
        ]
        return CaseExtraction(patient=reported.patient, adverse_events=adverse_events)
