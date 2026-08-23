"""Phase 3: company-assessed seriousness (企業評価 / ICH E2A).

Split by role, not by criterion (see ADR 0004):
- the **LLM interprets language** — reads the case text for the given adverse event
  and flags which E2A criteria are met, catching euphemisms (逝去→死亡,
  退院未定→入院延長) that keyword matching would miss;
- a **deterministic rule** turns the flags into the verdict — E2A is a logical OR
  ("any criterion → serious"), which is where auditability belongs. The verdict is
  traceable to *which criterion* and *which quote*.

Criterion 6 (医学的に重要) additionally fires deterministically when the event's
coded MedDRA PT is on the IME list. Uncertain-only signals → 要確認 (safe side, HITL)
rather than silently 非重篤 — the worst case is under-calling a serious event.
Assessed seriousness is kept separate from the reporter's transcribed value.
"""

import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.schemas import (
    AdverseEventMention,
    MeddraCoding,
    SeriousnessAssessment,
    SeriousnessCriterion,
    SeriousnessHit,
)
from app.services.ime import ImeReference

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（PV）の担当者です。症例テキストを読み、指定された有害事象に"
    "ついて、ICH E2A の重篤性基準に該当するかを判定してください。これは企業評価であり、"
    "報告者の記載（重篤/非重篤）とは独立に、症例の事実に基づいて判定します。\n"
    "重篤性の基準（いずれか該当で重篤）:\n"
    "・死亡: その有害事象により死亡した。婉曲表現も見落とさない（例:「逝去された」「亡くなった」）。\n"
    "・生命を脅かす: その事象の時点で死の危険があった（「もっと悪ければ危なかった」等の仮定は含めない）。\n"
    "・入院・入院期間の延長: 治療のための入院、または入院期間の延長。婉曲表現も拾う"
    "（例:「入院となった」「退院を予定していたが未定となった」「入院を要した」）。\n"
    "・障害: 永続的または重大な障害・機能不全。\n"
    "・先天異常: 後世代における先天異常・先天性欠損。\n"
    "・医学的に重要: 上記に直結しなくても、患者を危険にさらす／上記を防ぐため処置を要する"
    "医学的に重要な事象（例:アナフィラキシー、無顆粒球症、SJS/TEN、Torsades等）。\n"
    "重要な注意:\n"
    "・重篤性（serious）と重症度（severe＝症状の強さ）は別物。「重度の頭痛」でも入院・生命の危険等が"
    "無ければ重篤ではない。混同しない。\n"
    "・基準に該当する【肯定的な記述】が本文にある場合のみ、その基準を出力する。否定的記述"
    "（例:「対症療法を要さなかった」「入院しなかった」）や、記述が無いことを根拠に、疑いも含めて"
    "出力してはならない。\n"
    "・入院・入院期間の延長は、【その有害事象の治療・精査のために】入院した場合のみ該当。外来受診・"
    "対症療法・投与中止・経過観察のみは入院に該当しない。\n"
    "・入院・処置等が【別の有害事象】に対して行われた場合、それをこの有害事象に流用しない。この有害"
    "事象自身に帰属する事実のみを用いる（例:徐脈のための入院を、同じ症例のINR増加に適用しない）。\n"
    "・その有害事象が【入院中に発現】しても、入院の理由・延長の原因でなければ入院基準に該当しない"
    "（例:別事象での入院中に一過性に生じ、退院時に消失した事象）。\n"
    "・確実に該当は status=該当。肯定的記述はあるが帰属・程度に確信が持てない場合のみ status=疑い。"
    "該当しない基準は出力しない。\n"
    "・根拠は必ず本文の引用（evidence_quote）を添える。\n"
    "・rationale は日本語で簡潔に。"
)


class _CriterionHit(BaseModel):
    criterion: SeriousnessCriterion = Field(description="該当（または疑い）の重篤性基準。")
    status: Literal["該当", "疑い"] = Field(description="確実に該当＝該当、可能性はあるが不確実＝疑い。")
    evidence_quote: str | None = Field(default=None, description="症例テキストからの根拠引用。")


class _SeriousnessJudgment(BaseModel):
    hits: list[_CriterionHit] = Field(default_factory=list, description="該当/疑いの基準のみ。")
    rationale: str | None = Field(default=None, description="判定理由を日本語で簡潔に。")


class SeriousnessService:
    """Assess company seriousness per adverse event (LLM criteria + deterministic OR)."""

    def __init__(self, llm: BaseChatModel, ime: ImeReference) -> None:
        self.ime = ime
        self.chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    ("human", "症例テキスト:\n{case_text}\n\n判定対象の有害事象: {term}"),
                ]
            )
            | llm.with_structured_output(_SeriousnessJudgment)
        )

    def assess(
        self,
        case_text: str,
        adverse_events: list[AdverseEventMention],
        codings: list[MeddraCoding] | None = None,
    ) -> list[SeriousnessAssessment]:
        codings = codings or []
        return [
            self._assess_one(
                case_text, ae, codings[i] if i < len(codings) else None
            )
            for i, ae in enumerate(adverse_events)
        ]

    def _assess_one(
        self,
        case_text: str,
        ae: AdverseEventMention,
        coding: MeddraCoding | None,
    ) -> SeriousnessAssessment:
        judgment: _SeriousnessJudgment = self.chain.invoke(
            {"case_text": case_text, "term": ae.term}
        )
        confirmed = [
            SeriousnessHit(
                criterion=h.criterion, evidence_quote=h.evidence_quote, source="症例記述"
            )
            for h in judgment.hits
            if h.status == "該当"
        ]
        suspected = [
            SeriousnessHit(
                criterion=h.criterion, evidence_quote=h.evidence_quote, source="症例記述"
            )
            for h in judgment.hits
            if h.status == "疑い"
        ]

        # Deterministic criterion 6: coded PT on the IME list. Cite the PT and its
        # provenance (例示 / HITL昇格 <reviewer> <date> …) so the evidence explains
        # *why* it is medically important — incl. when it came from a past review.
        if (
            coding
            and self.ime.contains(coding.pt_code)
            and not any(h.criterion == "医学的に重要" for h in confirmed)
        ):
            quote = f"IME該当PT: {coding.pt_name_ja}（{coding.pt_code}）"
            provenance = self.ime.note(coding.pt_code)
            if provenance:
                quote += f" ／ {provenance}"
            confirmed.append(
                SeriousnessHit(
                    criterion="医学的に重要", evidence_quote=quote, source="IME"
                )
            )

        if confirmed:
            verdict, hits = "重篤", confirmed
        elif suspected:
            verdict, hits = "要確認", suspected
        else:
            verdict, hits = "非重篤", []

        return SeriousnessAssessment(
            term=ae.term,
            verdict=verdict,
            hits=hits,
            reported=ae.seriousness_reported,
            rationale=judgment.rationale,
        )
