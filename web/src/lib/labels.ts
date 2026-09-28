// Domain VALUES and their tones — the data side of the vocabulary.
//
// The API speaks Japanese values (重篤, 否定できない, ...) and the review form
// sends them back, so these lists are what is stored and validated. How a value
// is DISPLAYED lives in the i18n dictionaries: Japanese shows the value itself,
// English maps it via `values` in en.ts, which must cover every value listed
// here (KnownValue) — a new value without a translation fails the type check.

export type Tone = "danger" | "warn" | "good" | "muted";

// Allowed verdicts per review axis — mirrors backend ALLOWED_VERDICTS
// (services/triage_graph.py). A value outside these is rejected with 422.
// (Checked against the backend by backend/tests/test_frontend_contract.py.)
export const SER_OPTIONS = ["重篤", "非重篤", "要確認"] as const;
export const CAU_OPTIONS = ["否定できない", "否定できる", "評価不能"] as const;
export const EXP_OPTIONS = ["既知", "要確認", "未知", "判定不能"] as const;

// Other closed (or near-closed) vocabularies that reach the screen. Some are
// filled in by the model (match type, onset relation, sex, outcome); a value
// outside these lists is shown as-is rather than hidden.
export const CRITERIA = [
  "死亡", "生命を脅かす", "入院・入院期間の延長", "障害", "先天異常", "医学的に重要",
] as const;
export const CODED_BY = ["完全一致", "検索+LLM", "該当なし", "手動"] as const;
export const MATCH_TYPES = ["直接一致", "同義語", "読み替え・類似", "機序・文脈のみ", "該当なし"] as const;
export const ONSET_RELATIONS = ["投与開始前", "投与中", "投与中止後", "不明"] as const;
export const SEXES = ["女性", "男性", "不明"] as const;
export const OUTCOMES = ["軽快", "回復", "未回復", "後遺症あり", "死亡", "不明"] as const;
export const REPORTED_CAUSALITY = [
  "可能性あり（Possible）", "関連あり（Probable）", "関連なし（Unlikely）", "評価不能",
] as const;
export const IME_STATUSES = ["追加", "既存"] as const;
export const HIT_SOURCES = ["症例記述", "IME"] as const;

export type KnownValue =
  | (typeof SER_OPTIONS)[number]
  | (typeof CAU_OPTIONS)[number]
  | (typeof EXP_OPTIONS)[number]
  | (typeof CRITERIA)[number]
  | (typeof CODED_BY)[number]
  | (typeof MATCH_TYPES)[number]
  | (typeof ONSET_RELATIONS)[number]
  | (typeof SEXES)[number]
  | (typeof OUTCOMES)[number]
  | (typeof REPORTED_CAUSALITY)[number]
  | (typeof IME_STATUSES)[number]
  | (typeof HIT_SOURCES)[number];

// verdict → tone. In this domain the "danger" (red) tone marks the
// safety-conservative outcome (serious / stays in scope / unexpected).
const SERIOUSNESS_TONE: Record<string, Tone> = {
  重篤: "danger",
  要確認: "warn",
  非重篤: "muted",
};
const CAUSALITY_TONE: Record<string, Tone> = {
  否定できない: "danger",
  否定できる: "good",
  評価不能: "muted",
};
const EXPECTEDNESS_TONE: Record<string, Tone> = {
  既知: "good",
  要確認: "warn",
  未知: "danger",
  判定不能: "muted",
};

export function verdictTone(
  axis: "seriousness" | "causality" | "expectedness",
  verdict: string,
): Tone {
  const map =
    axis === "seriousness"
      ? SERIOUSNESS_TONE
      : axis === "causality"
        ? CAUSALITY_TONE
        : EXPECTEDNESS_TONE;
  return map[verdict] ?? "muted";
}

/** Coarse serious/non from the transcribed reporter value (非重篤 contains 重篤). */
export function reportedIsSerious(reported: string | null): boolean | null {
  if (!reported) return null;
  if (reported.includes("非重篤")) return false;
  if (reported.includes("重篤")) return true;
  return null;
}

/** Render a verdict→count dict as "重篤2／非重篤1" (or "—" when empty). The
 * caller formats each item and picks the separator, per language. */
export function counts(
  d: Record<string, number> | undefined,
  item: (value: string, n: number) => string,
  sep: string,
): string {
  if (!d || Object.keys(d).length === 0) return "—";
  return Object.entries(d)
    .map(([k, v]) => item(k, v))
    .join(sep);
}
