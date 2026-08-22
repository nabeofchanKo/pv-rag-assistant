"""Phase 3: temporal causality (因果関係), conservative triage posture.

This is a first-pass triage stance, NOT a full causality assessment: we do not try
to *prove* causality. An event that occurred after the suspect drug's administration
defaults to 否定できない (cannot be ruled out); we only conclude 否定できる (can be ruled
out) on a *clear* temporal incompatibility — onset before administration, or onset
after discontinuation when residual/delayed effects are also implausible.

Split by role (as in ADR 0004): the LLM classifies the temporal relationship and
supplies evidence; a deterministic rule maps it to the verdict, keeping the
conservative default (否定できない) and admitting exclusion only on the clear cases.
"""

import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.schemas import AdverseEventMention, CausalityAssessment

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（PV）の担当者です。トリアージの一次評価として、有害事象と"
    "被疑薬投与の【時間関係】から因果関係を保守的に評価します。因果を証明しにいくのではなく、"
    "「本剤投与後に発現したら基本的に否定できない」「明らかに時間的に否定できる時のみ否定できる」"
    "という姿勢です。\n"
    "手順:\n"
    "・被疑薬の投与開始日・投与終了日（中止日）と、有害事象の発現日を本文から特定する。\n"
    "・onset_relation を分類する:\n"
    "  - 投与開始前: 有害事象が投与開始より前から発現・存在していた。\n"
    "  - 投与中: 投与開始〜中止の期間内に発現した。\n"
    "  - 投与中止後: 投与中止より後に発現した。\n"
    "  - 不明: 日付が特定できず時間関係を確立できない。\n"
    "・clearly_excludable は【投与中止後】のときのみ意味を持つ。中止後の発現で、かつ薬剤の"
    "残存効果・遅発性の影響も想定し難く、明らかに時間的に不整合な場合のみ true。半減期が長い、"
    "遅発性が疑われる等の記述があれば false（否定できない）とする。\n"
    "・最終判定は当方のルールで決めるので、あなたは onset_relation と clearly_excludable、"
    "および根拠の抜き出しに専念する。\n"
    "・根拠（投与開始日・中止日・発現日など）は本文から evidence_quote に引用する。"
    "rationale は日本語で簡潔に。"
)


class _Judgment(BaseModel):
    onset_relation: Literal["投与開始前", "投与中", "投与中止後", "不明"] = Field(
        description="有害事象の発現時期（被疑薬投与に対する）。"
    )
    clearly_excludable: bool = Field(
        default=False,
        description="投与中止後の発現で、残存・遅発影響も想定し難く明らかに不整合な場合のみ true。",
    )
    evidence_quote: str | None = Field(default=None, description="判定根拠の本文引用。")
    rationale: str | None = Field(default=None, description="判定理由を日本語で簡潔に。")


# Deterministic mapping (conservative): default 否定できない; exclude only on the
# clear cases; 評価不能 only when the temporal relation can't be established.
def _verdict(onset_relation: str, clearly_excludable: bool) -> str:
    if onset_relation == "不明":
        return "評価不能"
    if onset_relation == "投与開始前":
        return "否定できる"
    if onset_relation == "投与中止後" and clearly_excludable:
        return "否定できる"
    return "否定できない"


class CausalityService:
    """Assess temporal causality per adverse event (conservative)."""

    def __init__(self, llm: BaseChatModel) -> None:
        self.chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    (
                        "human",
                        "被疑薬: {drugs}\n判定対象の有害事象: {term}（発現日: {onset}）\n\n"
                        "症例テキスト:\n{case_text}",
                    ),
                ]
            )
            | llm.with_structured_output(_Judgment)
        )

    def assess(
        self,
        case_text: str,
        adverse_events: list[AdverseEventMention],
        suspect_drugs: list[str] | None = None,
    ) -> list[CausalityAssessment]:
        drugs = "、".join(suspect_drugs) if suspect_drugs else "（本文の被疑薬）"
        return [self._assess_one(case_text, ae, drugs) for ae in adverse_events]

    def _assess_one(
        self, case_text: str, ae: AdverseEventMention, drugs: str
    ) -> CausalityAssessment:
        j: _Judgment = self.chain.invoke(
            {
                "drugs": drugs,
                "term": ae.term,
                "onset": ae.onset_date or "記載なし",
                "case_text": case_text,
            }
        )
        return CausalityAssessment(
            term=ae.term,
            verdict=_verdict(j.onset_relation, j.clearly_excludable),
            onset_relation=j.onset_relation,
            evidence_quote=j.evidence_quote,
            rationale=j.rationale,
        )
