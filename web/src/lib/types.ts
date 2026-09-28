// Mirrors the FastAPI response models in backend/app/schemas.py.
// Kept hand-written (small, stable contract) so the frontend has typed access
// to the backend without a codegen step. Computed fields (is_serious,
// is_expected, is_excludable, is_company_product_present) are serialized by
// Pydantic, so they appear in the JSON and are typed here as required.

// ---- RAG Q&A ----

/** One retrieved source chunk (backend: SourceInfo). */
export interface SourceInfo {
  document_name: string;
  page_number: number;
  chunk_index: number;
  text: string;
}

/** RAG answer with citations (backend: QueryResponse — POST /query). */
export interface QueryResponse {
  answer: string;
  query: string;
  sources: SourceInfo[];
}

/** Index result after upload (backend: UploadResponse — POST /documents/upload). */
export interface UploadResponse {
  document_name: string;
  chunks_added: number;
  message: string;
}

/** FastAPI error shape ({ "detail": ... }). */
export interface ApiError {
  detail: string;
}

// ---- Triage (POST /cases/triage) ----

export interface Patient {
  age: string | null;
  sex: string | null;
}

export type AeSource = "reported" | "narrative";

export interface AdverseEventMention {
  term: string;
  onset_date: string | null;
  outcome: string | null;
  seriousness_reported: string | null;
  source: AeSource;
}

export interface CaseExtraction {
  patient: Patient;
  adverse_events: AdverseEventMention[];
}

export interface ProductMatch {
  name: string;
  matched_via: string;
  active_ingredient: string | null;
  notes: string | null;
  label_document: string | null;
}

export interface ProductMatchResult {
  matched_products: ProductMatch[];
  is_company_product_present: boolean; // computed
}

export interface MeddraTerm {
  pt_code: string;
  pt_name_ja: string;
  pt_name_en: string | null;
  soc_name_ja: string | null;
}

export type MeddraCodedBy = "完全一致" | "検索+LLM" | "該当なし" | "手動";

export interface MeddraCoding {
  term: string;
  pt_code: string | null;
  pt_name_ja: string | null;
  pt_name_en: string | null; // display only (English UI); null for a reviewer-typed PT
  soc_name_ja: string | null;
  coded_by: MeddraCodedBy;
  rationale: string | null;
  candidates: MeddraTerm[];
}

export type SeriousnessVerdict = "重篤" | "非重篤" | "要確認";

export interface SeriousnessHit {
  criterion: string;
  evidence_quote: string | null;
  source: "症例記述" | "IME";
}

export interface SeriousnessAssessment {
  term: string;
  verdict: SeriousnessVerdict;
  hits: SeriousnessHit[];
  reported: string | null;
  rationale: string | null;
  is_serious: boolean; // computed
}

export type CausalityVerdict = "否定できない" | "否定できる" | "評価不能";

export interface CausalityAssessment {
  term: string;
  verdict: CausalityVerdict;
  onset_relation: string | null;
  evidence_quote: string | null;
  rationale: string | null;
  is_excludable: boolean; // computed
}

export type ExpectednessVerdict = "既知" | "要確認" | "未知" | "判定不能";

export interface ExpectednessAssessment {
  term: string;
  verdict: ExpectednessVerdict;
  match_type: string | null;
  rationale: string | null;
  evidence_quote: string | null;
  evidence_section: string | null;
  is_expected: boolean; // computed
}

export interface DrugExpectedness {
  drug_name: string;
  label_document: string;
  assessments: ExpectednessAssessment[];
}

export interface EventPrecedent {
  term: string;
  pt_code: string | null;
  n_cases: number;
  seriousness: Record<string, number>;
  causality: Record<string, number>;
  expectedness: Record<string, number>;
  case_ids: string[];
  conflicts: string[];
}

export type ReviewAxis = "seriousness" | "causality" | "expectedness";

export interface InfluenceItem {
  axis: string;
  term: string;
  source: string; // "IME" | "precedent"
  applied: boolean;
  drug_name: string | null;
  from_verdict: string | null;
  to_verdict: string | null;
  note: string;
}

export interface Escalation {
  axis: ReviewAxis;
  term: string;
  drug_name: string | null;
  verdict: string;
  reason: string;
}

// ---- Phase 6: per-run cost / latency (backend: RunTelemetry) ----

/** One graph step's share of a run. Deterministic steps have zero tokens. */
export interface StepTelemetry {
  step: string;
  started_ms: number; // offset from run start — parallel steps overlap
  latency_ms: number;
  llm_calls: number;
  models: string[];
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cost_usd: number | null; // null = a model this step used has no price entry
}

/** Measured tokens / cost / time of one triage run (chat models only). */
export interface RunTelemetry {
  wall_ms: number;
  steps: StepTelemetry[];
  pricing_as_of: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  cost_complete: boolean;
}

/** Shared triage content — the fields common to TriageDraft and TriageResult. */
export interface TriageContent {
  document_name: string;
  product_match: ProductMatchResult;
  extraction: CaseExtraction;
  meddra: MeddraCoding[];
  seriousness: SeriousnessAssessment[];
  causality: CausalityAssessment[];
  expectedness: DrugExpectedness[];
  precedent: EventPrecedent[];
  influence_mode: string;
  influence: InfluenceItem[];
  source_text: string;
  telemetry: RunTelemetry | null;
}

/** Start response, paused for review (backend: TriageDraft). */
export interface TriageDraft extends TriageContent {
  thread_id: string;
  status: "awaiting_review";
  escalations: Escalation[];
}

// ---- HITL review (POST /cases/{thread_id}/approve) ----

/** A reviewer's override of one per-AE verdict. drug_name is required for
 * expectedness (which label the verdict belongs to). */
export interface VerdictOverride {
  axis: ReviewAxis;
  term: string;
  drug_name?: string | null;
  new_verdict: string;
  rationale?: string | null;
}

/** A PT to add to the IME list — future events coded to it fire E2A criterion 6. */
export interface ImePromotion {
  pt_code: string;
  pt_name: string;
  rationale?: string | null;
}

/** A reviewer-added adverse event (manual verdicts; no machine re-assessment). */
export interface AddedEvent {
  term: string;
  pt_code?: string | null;
  pt_name?: string | null;
  seriousness: string;
  causality: string;
}

/** A reviewer's MedDRA PT correction for an existing event. */
export interface RecodedEvent {
  term: string;
  pt_code: string;
  pt_name: string;
}

/** Body of POST /cases/{thread_id}/approve (backend: ReviewDecision). */
export interface ReviewDecision {
  action: "approve" | "reject";
  reviewer: string;
  note?: string | null;
  overrides: VerdictOverride[];
  ime_promotions: ImePromotion[];
  removed_terms: string[];
  added_events: AddedEvent[];
  recoded: RecodedEvent[];
}

/** Audit entry: what a reviewer changed, keeping the original verdict. */
export interface OverrideRecord {
  axis: ReviewAxis;
  term: string;
  drug_name: string | null;
  original_verdict: string;
  new_verdict: string;
  rationale: string | null;
}

/** Audit entry for a PT promoted to the IME list during a review. */
export interface ImePromotionRecord {
  pt_code: string;
  pt_name: string;
  reviewer: string;
  promoted_at: string;
  rationale: string | null;
  status: "追加" | "既存";
}

/** Audit entry for a reviewer's extraction edit. */
export interface ExtractionEditRecord {
  kind: "removed" | "added" | "recoded";
  term: string;
  detail: string | null;
}

/** The finalized review attached to an approved/rejected result. */
export interface ReviewOutcome {
  status: "approved" | "rejected";
  reviewer: string;
  note: string | null;
  overrides: OverrideRecord[];
  ime_promotions: ImePromotionRecord[];
  extraction_edits: ExtractionEditRecord[];
  reviewed_at: string;
}

/** Finalized result with audit trail (backend: TriageResult). */
export interface TriageResult extends TriageContent {
  thread_id: string;
  status: "approved" | "rejected";
  review: ReviewOutcome;
}

/** Hard-gated out-of-scope case (backend: OutOfScopeResult). */
export interface OutOfScopeResult {
  thread_id: string;
  status: "out_of_scope";
  product_match: ProductMatchResult;
  reason: string;
  source_text: string;
  telemetry: RunTelemetry | null;
}

/** Discriminated union returned by POST /cases/triage. */
export type TriageStartResponse = TriageDraft | TriageResult | OutOfScopeResult;
