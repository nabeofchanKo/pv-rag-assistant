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
        description=(
            "有害事象の名称。報告書の記載どおりに、修飾語（部位・性状・程度等）も省略せず"
            "転記する（例：頭痛（重度）、そう痒症（全身性）、鼻出血（反復性）、徐脈（症候性））。"
            "併記された英語名（例：（Pruritus））は含めない。"
        ),
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
    coded_by: Literal["完全一致", "検索+LLM", "該当なし", "手動"] = Field(
        description="由来。完全一致＝辞書と一致し決定的、検索+LLM＝候補からLLMが選択、該当なし＝適合PTなし、手動＝レビュアーが付与/修正。",
    )
    rationale: str | None = None
    # The candidates considered (fused hybrid retrieval), kept for HITL / audit.
    candidates: list[MeddraTerm] = []


# --- Phase 3 (slice 3c): seriousness assessment (企業評価 / ICH E2A) ---
# The LLM interprets the case text for each E2A criterion (catching euphemisms like
# 逝去→死亡, 退院未定→入院延長) and emits structured criterion hits with evidence;
# a deterministic OR then decides 重篤/非重篤. Uncertain-only -> 要確認 (safe side,
# HITL). This is the company frame, kept distinct from the reporter's transcribed
# seriousness_reported so the two can be compared.

SeriousnessCriterion = Literal[
    "死亡", "生命を脅かす", "入院・入院期間の延長", "障害", "先天異常", "医学的に重要"
]


class SeriousnessHit(BaseModel):
    criterion: SeriousnessCriterion = Field(description="該当したICH E2Aの重篤性基準。")
    evidence_quote: str | None = Field(
        default=None, description="該当の根拠とした症例テキストの引用。"
    )
    source: Literal["症例記述", "IME"] = Field(
        default="症例記述",
        description="判定の出所。症例記述＝本文から、IME＝コード化PTが医学的に重要事象リストに該当。",
    )


class SeriousnessAssessment(BaseModel):
    term: str
    verdict: Literal["重篤", "非重篤", "要確認"] = Field(
        description="企業評価。重篤＝基準1つ以上に該当、要確認＝疑いのみ(安全側でHITL)、非重篤＝該当なし。",
    )
    hits: list[SeriousnessHit] = []
    reported: str | None = Field(
        default=None, description="報告上の重篤度（転記, seriousness_reported）。ズレ確認用。"
    )
    rationale: str | None = None

    @computed_field
    @property
    def is_serious(self) -> bool:
        """Only 重篤 counts as serious. 要確認/非重篤 must not be treated as serious —
        but 要確認 is surfaced for HITL rather than silently dropped to 非重篤."""
        return self.verdict == "重篤"


# --- Phase 3 (slice 3d): causality assessment (因果関係, temporal / conservative) ---
# Triage posture (not a full causality proof): an event that occurred AFTER
# administration defaults to 否定できない (cannot rule out); 否定できる (can rule out)
# only on clear temporal incompatibility — onset before administration, or onset
# after discontinuation when residual/delayed effects are also implausible.


class CausalityAssessment(BaseModel):
    term: str
    verdict: Literal["否定できない", "否定できる", "評価不能"] = Field(
        description=(
            "否定できない＝投与後に発現し因果を否定できない(既定・保守的)、"
            "否定できる＝明らかに時間的に不整合、評価不能＝日付不明で時間関係を確立できない。"
        ),
    )
    onset_relation: str | None = Field(
        default=None,
        description="投与に対する発現時期（投与開始前／投与中／投与中止後／不明）。",
    )
    evidence_quote: str | None = Field(
        default=None, description="投与開始日・中止日・発現日など、判定根拠の本文引用。"
    )
    rationale: str | None = None

    @computed_field
    @property
    def is_excludable(self) -> bool:
        """True only for 否定できる. 否定できない/評価不能 stay in scope (conservative)."""
        return self.verdict == "否定できる"


# --- Phase 2 (slice 2c) / Phase 3: combined triage output ---


class TriageResponse(BaseModel):
    document_name: str
    product_match: ProductMatchResult
    extraction: CaseExtraction
    # MedDRA PT suggestion per extracted adverse event (aligned to adverse_events order).
    meddra: list[MeddraCoding] = []
    # Company-assessed seriousness per adverse event (aligned to adverse_events order).
    seriousness: list[SeriousnessAssessment] = []
    # Temporal causality per adverse event (conservative; aligned to adverse_events order).
    causality: list[CausalityAssessment] = []
    # One entry per matched own-company product that has a package insert.
    # Empty when no matched product has a label (expectedness not assessable).
    expectedness: list[DrugExpectedness] = []
    # Per-adverse-event precedent from past approved cases (Phase 4d; advisory).
    precedent: list["EventPrecedent"] = []
    # Phase 4e: whether past data (IME + precedent) was folded into the verdicts
    # ("applied") or only shown as notes ("advisory"), and the resulting effects.
    influence_mode: str = "applied"
    influence: list["InfluenceItem"] = []
    source_text: str


# --- Phase 4d: past-case precedent (structured per-(drug, PT) lookup) ---
# Advisory only: precedent surfaces how similar past cases were judged (and flags
# where the current draft disagrees) for cross-case consistency. It NEVER changes
# a verdict automatically — the human decides (unlike the IME list, which fires
# criterion 6 deterministically). See ADR 0009.


class EventPrecedent(BaseModel):
    """How past approved cases judged this event's PT, aligned to adverse_events."""

    term: str
    pt_code: str | None = None
    n_cases: int = 0
    seriousness: dict[str, int] = {}   # past verdict -> count
    causality: dict[str, int] = {}
    expectedness: dict[str, int] = {}
    case_ids: list[str] = []
    # Axes ("seriousness" / "causality") where the current draft verdict differs
    # from the precedent majority.
    conflicts: list[str] = []


class PastCaseEvent(BaseModel):
    """One event of a stored past case (a compact, decision-relevant summary)."""

    term: str
    pt_code: str | None = None
    pt_name: str | None = None
    seriousness: str | None = None
    causality: str | None = None
    expectedness: dict[str, str] = {}   # drug -> verdict


class PastCaseRecord(BaseModel):
    """A finalized (approved) case persisted as precedent for future triage."""

    case_id: str
    date: str | None = None
    drugs: list[str] = []
    reviewer: str | None = None
    events: list[PastCaseEvent] = []


# --- Phase 4e: past-data influence mode (applied / advisory) ---
# One toggle unifies both past-data sources — the IME list (past feedback) and
# past-case precedent. "applied" folds them into the verdicts (IME → criterion 6
# = 重篤 deterministically, since it's an explicit prior human decision; precedent
# → a safe-side nudge to 要確認 only, never a downgrade). "advisory" leaves the
# fresh verdicts untouched and records the same signals as notes. See ADR 0010.


class InfluenceItem(BaseModel):
    """One past-data effect on an event — an applied adjustment or an advisory note."""

    axis: str  # "seriousness" | "causality" | "expectedness"
    term: str
    source: str  # "IME" | "precedent"
    applied: bool  # True = changed the verdict; False = advisory note only
    drug_name: str | None = None  # set for expectedness (which label)
    from_verdict: str | None = None  # set when applied
    to_verdict: str | None = None  # set when applied
    note: str


# TriageResponse forward-references EventPrecedent / InfluenceItem (defined above
# and below); resolve them once both exist.
TriageResponse.model_rebuild()


# --- Phase 4b: HITL approval (propose → approve) over the triage graph ---
# The graph produces a triage draft, pauses at a human-review interrupt, and a
# reviewer approves (optionally overriding the per-AE judgment verdicts) or
# rejects. Every override keeps the original value, so the record is auditable —
# essential in a regulated (safety-reporting) workflow.

ReviewAxis = Literal["seriousness", "causality", "expectedness"]


class Escalation(BaseModel):
    """A draft item the reviewer should look at (safe-side uncertain bands)."""

    axis: ReviewAxis
    term: str
    drug_name: str | None = None  # set for expectedness (which label)
    verdict: str
    reason: str


class VerdictOverride(BaseModel):
    """A reviewer's override of one per-AE verdict (submitted with /approve)."""

    axis: ReviewAxis
    term: str
    drug_name: str | None = Field(
        default=None, description="expectedness の上書き時のみ必須（どの添付文書か）。"
    )
    new_verdict: str = Field(description="上書き後の判定。対象軸の許容値のいずれか。")
    rationale: str | None = Field(default=None, description="上書きの理由（日本語で簡潔に）。")


class ImePromotion(BaseModel):
    """A reviewer's request to add a MedDRA PT to the IME list (Phase 4c).

    Promoting a PT makes future events coded to it fire E2A criterion 6 (医学的に
    重要) automatically — the reviewer's judgment fed back into later accuracy."""

    pt_code: str = Field(description="昇格するPTのMedDRAコード（コード化済みの事象のみ）。")
    pt_name: str = Field(description="PT名（監査・CSV記録用）。")
    rationale: str | None = Field(default=None, description="昇格の理由（日本語で簡潔に）。")


class AddedEvent(BaseModel):
    """A reviewer-added adverse event (manual — no machine re-assessment; Phase 4f)."""

    term: str
    pt_code: str | None = None
    pt_name: str | None = None
    seriousness: str = Field(default="要確認", description="重篤度（既定は安全側の要確認）。")
    causality: str = Field(default="否定できない", description="因果（既定は保守的な否定できない）。")


class RecodedEvent(BaseModel):
    """A reviewer's MedDRA PT correction for an existing event (Phase 4f)."""

    term: str
    pt_code: str
    pt_name: str


class ReviewDecision(BaseModel):
    """The reviewer's decision — the body of POST /cases/{thread_id}/approve and
    the resume payload handed back into the graph."""

    action: Literal["approve", "reject"]
    reviewer: str = Field(description="レビュー担当者の識別子（監査用）。")
    note: str | None = Field(default=None, description="全体所見（任意）。")
    overrides: list[VerdictOverride] = Field(
        default_factory=list, description="承認時に適用する判定の上書き（0件可）。"
    )
    ime_promotions: list[ImePromotion] = Field(
        default_factory=list,
        description="承認時にIMEリストへ昇格するPT（今後の症例のcriterion 6に反映）。0件可。",
    )
    # Phase 4f: extraction edits (manual; applied deterministically, no re-run).
    removed_terms: list[str] = Field(
        default_factory=list, description="誤抽出として削除する有害事象の term。"
    )
    added_events: list[AddedEvent] = Field(
        default_factory=list, description="見落としとして追加する有害事象（判定は手入力）。"
    )
    recoded: list[RecodedEvent] = Field(
        default_factory=list, description="MedDRA PT を修正する事象。"
    )


class OverrideRecord(BaseModel):
    """Audit entry: what a reviewer changed, keeping the original verdict."""

    axis: ReviewAxis
    term: str
    drug_name: str | None = None
    original_verdict: str
    new_verdict: str
    rationale: str | None = None


class ImePromotionRecord(BaseModel):
    """Audit entry for a PT promoted to the IME list during a review (Phase 4c)."""

    pt_code: str
    pt_name: str
    reviewer: str
    promoted_at: datetime
    rationale: str | None = None
    status: Literal["追加", "既存"] = Field(
        description="追加＝新規にIMEへ登録、既存＝すでに登録済み（重複追記なし）。"
    )


class ExtractionEditRecord(BaseModel):
    """Audit entry for a reviewer's extraction edit (removed/added/recoded)."""

    kind: Literal["removed", "added", "recoded"]
    term: str
    detail: str | None = None


class ReviewOutcome(BaseModel):
    """The finalized review — attached to the approved/rejected result."""

    status: Literal["approved", "rejected"]
    reviewer: str
    note: str | None = None
    overrides: list[OverrideRecord] = []
    ime_promotions: list[ImePromotionRecord] = []
    extraction_edits: list[ExtractionEditRecord] = []
    reviewed_at: datetime


class TriageDraft(TriageResponse):
    """Start response: the full triage draft, paused for human review."""

    thread_id: str
    status: Literal["awaiting_review"] = "awaiting_review"
    escalations: list[Escalation] = []


class TriageResult(TriageResponse):
    """Approve/reject response: the finalized triage with its audit trail."""

    thread_id: str
    status: Literal["approved", "rejected"]
    review: ReviewOutcome


class OutOfScopeResult(BaseModel):
    """Returned when no own-company product is involved — the case is hard-gated
    out and NO evaluation (extraction / MedDRA / the four judgments) is run
    (Phase 4g). Own-company scoping is a prerequisite for company assessment."""

    thread_id: str
    status: Literal["out_of_scope"] = "out_of_scope"
    product_match: ProductMatchResult
    reason: str = "自社品が使用されていないため評価対象外（自社品判定でヒットなし）"
    source_text: str
