"""Define domain models for the PDF processing service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class AdverseEventMention(BaseModel):
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


class CaseExtraction(BaseModel):
    patient: Patient = Field(description="患者の基本情報。")
    adverse_events: list[AdverseEventMention] = Field(
        description="症例から抽出した有害事象の一覧（経過の記述から読み取れるものも含む）。",
    )
