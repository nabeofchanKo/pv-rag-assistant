"""Define domain models for the PDF processing service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

class PageContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int
    text: str
    char_count: int
    extraction_method: str = "text"


class ProcessedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_name: str
    page_count: int
    pages: list[PageContent]
    processed_at: datetime

    @property
    def full_text(self) -> str:
        """Concatenate all page texts and return as a single string."""
        return "\n\n".join(page.text for page in self.pages)


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_name: str
    chunk_index: int
    page_number: int
    total_chunks: int
    char_start: int
    char_end: int
    text: str
    created_at: datetime
    language: str = "ja"


class RAGResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    source_chunks: list[Chunk]
    query: str


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3


class SourceInfo(BaseModel):
    document_name: str
    page_number: int
    chunk_index: int
    text: str


class QueryResponse(BaseModel):
    answer: str
    query: str
    sources: list[SourceInfo]


class UploadResponse(BaseModel):
    document_name: str
    chunks_added: int
    message: str


# --- Phase 2 (slice 1): structured extraction models ---
# Fields are extracted "as reported" (raw strings, no normalization); the Field
# descriptions double as the extraction instructions for the LLM. A validator
# coerces stray "null"/"none"/empty strings from the model into real None.


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
        return None
    return value


class Patient(BaseModel):
    age: str | None = Field(
        default=None,
        description="患者の年齢。原文の表記のまま（例：58歳）。記載がなければ省略。",
    )
    sex: str | None = Field(
        default=None,
        description="患者の性別（女性／男性／不明）。記載がなければ省略。",
    )

    @field_validator("age", "sex", mode="before")
    @classmethod
    def _coerce_blank(cls, v: object) -> object:
        return _blank_to_none(v)


class AdverseEventCore(BaseModel):
    term: str = Field(
        description="有害事象の名称。報告書の記載どおりに（例：頭痛、嘔吐、肝機能異常）。",
    )
    onset_date: str | None = Field(
        default=None,
        description="発現日。原文の表記のまま（例：2025/08/10）。記載がなければ省略。",
    )
    outcome: str | None = Field(
        default=None,
        description="転帰（例：軽快、回復、未回復、不明）。記載がなければ省略。",
    )
    seriousness_reported: str | None = Field(
        default=None,
        description="報告書に記載された重篤度（重篤／非重篤）。自分で判定はせず、記載がある場合のみ転記。なければ省略。",
    )

    @field_validator("onset_date", "outcome", "seriousness_reported", mode="before")
    @classmethod
    def _coerce_blank(cls, v: object) -> object:
        return _blank_to_none(v)


class AdverseEventMention(AdverseEventCore):
    source: Literal["reported", "narrative"] = Field(
        description=(
            "この有害事象の出典。「有害事象」欄など明記された箇所から取った場合は "
            '"reported"、経過（ナラティブ）の記述から読み取った場合は "narrative"。'
        ),
    )


class CaseExtraction(BaseModel):
    patient: Patient = Field(description="患者の基本情報。")
    adverse_events: list[AdverseEventMention] = Field(
        description="症例から抽出した有害事象の一覧（経過の記述から読み取れるものも含む）。",
    )


# --- Phase 2 (slice 2b): own-company product matching (自社品判定) ---


class ProductMatch(BaseModel):
    name: str
    matched_via: str          # the token (name / ingredient / alias) that hit the text
    active_ingredient: str | None = None
    notes: str | None = None
    # Package-insert file (in data/drug_labels/) used as the expectedness RAG source.
    label_document: str | None = None


class ProductMatchResult(BaseModel):
    matched_products: list[ProductMatch]

    @computed_field
    @property
    def is_company_product_present(self) -> bool:
        """True if any own-company product was found (i.e. the case is in scope)."""
        return len(self.matched_products) > 0


# --- Phase 3 (slice 3a): expectedness (既知/未知) assessment ---
# Judgment, NOT transcription: is each adverse event already described in the
# suspect drug's package insert (添付文書)? Assessed by RAG over the label text,
# kept separate from the faithful extraction above (extraction never judges).


class ExpectednessAssessment(BaseModel):
    term: str = Field(description="判定対象の有害事象名（抽出結果の term をそのまま用いる）。")
    verdict: Literal["既知", "要確認", "未知", "判定不能"] = Field(
        description=(
            "既知＝記載あり(確信)、要確認＝該当しうる記載はあるが確信度が低く安全側で未知扱い(要HITL)、"
            "未知＝記載なし、判定不能＝提示された記載だけでは決められない。"
        ),
    )
    match_type: str | None = Field(
        default=None,
        description="一致の種類（直接一致／同義語／読み替え・類似／機序・文脈のみ／該当なし）。判定の根拠区分。",
    )
    rationale: str | None = Field(
        default=None, description="判定の理由（記載箇所の要約など）。日本語で簡潔に。"
    )
    evidence_quote: str | None = Field(
        default=None,
        description="根拠とした添付文書中の該当箇所（引用）。既知・要確認では該当引用を保持。",
    )
    evidence_section: str | None = Field(
        default=None,
        description='該当した項目名（例："11.1 重大な副作用" / "11.2 その他の副作用" / "10. 相互作用"）。特定できれば。',
    )

    @computed_field
    @property
    def is_expected(self) -> bool:
        """Only 既知 counts as expected. 要確認/未知/判定不能 must NOT be treated as
        expected downstream — the worst case is an unexpected serious event with a
        short reporting deadline being buried under an over-eager 既知."""
        return self.verdict == "既知"


class DrugExpectedness(BaseModel):
    """Expectedness of every adverse event against one suspect drug's label."""

    drug_name: str
    label_document: str
    assessments: list[ExpectednessAssessment]


# --- Phase 3 (slice 3b): MedDRA PT coding ---


class MeddraTerm(BaseModel):
    """One MedDRA Preferred Term row from the dictionary."""

    model_config = ConfigDict(frozen=True)

    pt_code: str
    pt_name_ja: str
    pt_name_en: str | None = None
    soc_name_ja: str | None = None


class MeddraCoding(BaseModel):
    """MedDRA PT suggestion for one adverse-event term (per-AE, drug-independent)."""

    term: str
    pt_code: str | None = None
    pt_name_ja: str | None = None
    soc_name_ja: str | None = None
    coded_by: Literal["完全一致", "検索+LLM", "該当なし"] = Field(
        description="由来。完全一致＝辞書と一致し決定的、検索+LLM＝候補からLLMが選択、該当なし＝適合PTなし。",
    )
    rationale: str | None = None
    # The candidates considered (fused hybrid retrieval), kept for HITL / audit.
    candidates: list[MeddraTerm] = []


# --- Phase 2 (slice 2c) / Phase 3: combined triage output ---


class TriageResponse(BaseModel):
    document_name: str
    product_match: ProductMatchResult
    extraction: CaseExtraction
    # MedDRA PT suggestion per extracted adverse event (aligned to adverse_events order).
    meddra: list[MeddraCoding] = []
    # One entry per matched own-company product that has a package insert.
    # Empty when no matched product has a label (expectedness not assessable).
    expectedness: list[DrugExpectedness] = []
    source_text: str
