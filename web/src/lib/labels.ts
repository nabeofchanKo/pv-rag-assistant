// Display labels + verdict→tone mapping, mirroring frontend/app.py so the
// Next.js triage view reads the same as the Streamlit one it replaces.

export type Tone = "danger" | "warn" | "good" | "muted";

export const SOURCE_LABELS: Record<string, string> = {
  reported: "報告済み",
  narrative: "経過から読取り",
};

export const AXIS_LABELS: Record<string, string> = {
  seriousness: "重篤度",
  causality: "因果関係",
  expectedness: "既知/未知",
};

export const INFLUENCE_SOURCE_LABELS: Record<string, string> = {
  IME: "以前のFB(IME)",
  precedent: "過去症例",
};

export const EXTRACTION_EDIT_KIND_LABELS: Record<string, string> = {
  removed: "削除",
  added: "追加",
  recoded: "PT修正",
};

// Allowed verdicts per review axis — mirrors backend ALLOWED_VERDICTS
// (services/triage_graph.py). A value outside these is rejected with 422.
export const SER_OPTIONS = ["重篤", "非重篤", "要確認"];
export const CAU_OPTIONS = ["否定できない", "否定できる", "評価不能"];
export const EXP_OPTIONS = ["既知", "要確認", "未知", "判定不能"];

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

/** Render a verdict→count dict as "重篤2／非重篤1" (or "—" when empty). */
export function counts(d: Record<string, number> | undefined): string {
  if (!d || Object.keys(d).length === 0) return "—";
  return Object.entries(d)
    .map(([k, v]) => `${k}${v}`)
    .join("／");
}

// Triage graph node → display name (cost / latency panel).
export const STEP_LABELS: Record<string, string> = {
  product_match: "自社品判定",
  out_of_scope: "評価対象外ゲート",
  extraction: "有害事象の抽出",
  meddra: "MedDRAコード化",
  seriousness: "重篤度",
  causality: "因果関係",
  expectedness: "既知/未知",
  precedent: "過去症例の参照",
  influence: "過去データの反映",
};
