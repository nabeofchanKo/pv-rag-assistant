// Build a synthetic ICSR from a constrained form.
//
// The point is to let someone who knows PV construct a targeted case — e.g. a
// dizziness reported as non-serious, whose narrative mentions a fall, a fracture
// and admission — and check whether the company assessment correctly upgrades it
// to serious on the hospitalisation criterion. That is the hardest behaviour in
// the pipeline (narrative attribution) and the one worth demonstrating.
//
// The CLIENT never composes the report text: it sends these fields and the BFF
// renders the document server-side. That keeps the public demo constrained
// (fixed drug list, enumerated verdicts, capped narrative) without accepting an
// arbitrary upload, and keeps the generated format consistent with the bundled
// samples so extraction behaves the same way.

/** Mirrors data/product_master/products.yaml. DrugA is deliberately NOT in the
 * master, so picking it exercises the own-company hard gate (out_of_scope). */
export const BUILDER_DRUGS = [
  {
    name: "DrugX",
    ingredient: "Compound-X",
    indication: "本態性高血圧",
    ownCompany: true,
  },
  {
    name: "DrugY",
    ingredient: "Compound-Y",
    indication: "2型糖尿病",
    ownCompany: true,
  },
  {
    name: "DrugZ",
    ingredient: "Compound-Z",
    indication: "心房細動",
    ownCompany: true,
  },
  {
    name: "DrugA",
    ingredient: "Compound-A",
    indication: "うつ病",
    ownCompany: false,
  },
] as const;

export const SEX_OPTIONS = ["女性", "男性", "不明"];
export const OUTCOME_OPTIONS = ["軽快", "回復", "未回復", "後遺症あり", "死亡", "不明"];
export const REPORTED_SERIOUSNESS_OPTIONS = ["非重篤", "重篤"];
export const REPORTED_CAUSALITY_OPTIONS = [
  "可能性あり（Possible）",
  "関連あり（Probable）",
  "関連なし（Unlikely）",
  "評価不能",
];

export const BUILDER_LIMITS = {
  maxEvents: 8,
  maxTerm: 80,
  maxField: 40,
  maxNarrative: 2000,
};

export type BuiltEvent = {
  term: string;
  onset: string;
  outcome: string;
  seriousness: string;
};

export type CaseDraft = {
  drug: string;
  age: string;
  sex: string;
  startDate: string;
  endDate: string;
  reportedCausality: string;
  events: BuiltEvent[];
  narrative: string;
};

export const EMPTY_EVENT: BuiltEvent = {
  term: "",
  onset: "",
  outcome: "軽快",
  seriousness: "非重篤",
};

export const EMPTY_DRAFT: CaseDraft = {
  drug: "DrugX",
  age: "",
  sex: "女性",
  startDate: "",
  endDate: "",
  reportedCausality: REPORTED_CAUSALITY_OPTIONS[0],
  events: [{ ...EMPTY_EVENT }],
  narrative: "",
};

/** The case worth showing first: reported as non-serious, but the narrative
 * describes a fall, a fracture and admission — the company assessment should
 * come back 重篤 on the hospitalisation criterion. */
export const PRESET_DRAFT: CaseDraft = {
  drug: "DrugX",
  age: "78歳",
  sex: "女性",
  startDate: "2026-01-10",
  endDate: "2026-02-02",
  reportedCausality: REPORTED_CAUSALITY_OPTIONS[0],
  events: [
    { term: "浮動性めまい", onset: "2026-01-14", outcome: "回復", seriousness: "非重篤" },
  ],
  narrative:
    "本態性高血圧に対し2026-01-10よりDrugX 10 mgの1日1回投与を開始した。" +
    "投与開始から4日後（2026-01-14）、患者は立ち上がった際に浮動性めまいを自覚した。" +
    "報告者はこれを軽微なものと考え、重篤度は非重篤として報告している。\n\n" +
    "しかし同日夕刻、自宅の廊下でめまいのため転倒し、右大腿骨頸部骨折を受傷した。" +
    "救急搬送のうえ同日入院し、翌日に観血的整復固定術が施行された。" +
    "入院期間は18日間に及び、2026-02-02に退院した。DrugXは入院時に投与中止とされた。",
};

const stripNewlines = (v: string) => v.replace(/[\r\n]+/g, " ").trim();

function clean(v: unknown, max: number): string {
  if (typeof v !== "string") return "";
  return stripNewlines(v).slice(0, max);
}

export type ValidationResult =
  | { ok: true; draft: CaseDraft }
  | { ok: false; error: string };

/** Validate and normalise an untrusted payload from the browser. */
export function validateDraft(input: unknown): ValidationResult {
  if (!input || typeof input !== "object") {
    return { ok: false, error: "症例データが不正です。" };
  }
  const raw = input as Record<string, unknown>;

  const drug = BUILDER_DRUGS.find((d) => d.name === raw.drug);
  if (!drug) return { ok: false, error: "薬剤は一覧から選択してください。" };

  const rawEvents = Array.isArray(raw.events) ? raw.events : [];
  const events: BuiltEvent[] = [];
  for (const e of rawEvents) {
    if (!e || typeof e !== "object") continue;
    const r = e as Record<string, unknown>;
    const term = clean(r.term, BUILDER_LIMITS.maxTerm);
    if (!term) continue;
    events.push({
      term,
      onset: clean(r.onset, BUILDER_LIMITS.maxField),
      outcome: OUTCOME_OPTIONS.includes(String(r.outcome)) ? String(r.outcome) : "不明",
      seriousness: REPORTED_SERIOUSNESS_OPTIONS.includes(String(r.seriousness))
        ? String(r.seriousness)
        : "非重篤",
    });
  }
  if (events.length === 0) {
    return { ok: false, error: "有害事象を1件以上入力してください。" };
  }
  if (events.length > BUILDER_LIMITS.maxEvents) {
    return {
      ok: false,
      error: `有害事象は ${BUILDER_LIMITS.maxEvents} 件までです。`,
    };
  }

  return {
    ok: true,
    draft: {
      drug: drug.name,
      age: clean(raw.age, BUILDER_LIMITS.maxField),
      sex: SEX_OPTIONS.includes(String(raw.sex)) ? String(raw.sex) : "不明",
      startDate: clean(raw.startDate, BUILDER_LIMITS.maxField),
      endDate: clean(raw.endDate, BUILDER_LIMITS.maxField),
      reportedCausality: REPORTED_CAUSALITY_OPTIONS.includes(String(raw.reportedCausality))
        ? String(raw.reportedCausality)
        : "評価不能",
      events,
      narrative:
        typeof raw.narrative === "string"
          ? raw.narrative.slice(0, BUILDER_LIMITS.maxNarrative).trim()
          : "",
    },
  };
}

const orDash = (v: string) => (v ? v : "記載なし");

/** Render the validated draft in the same layout as the bundled sample cases. */
export function renderIcsr(draft: CaseDraft): string {
  const drug = BUILDER_DRUGS.find((d) => d.name === draft.drug)!;
  const today = new Date().toISOString().slice(0, 10);

  const events = draft.events
    .map(
      (e, i) =>
        `事象${i + 1}：${e.term}\n` +
        `　発現日：${orDash(e.onset)}\n` +
        `　転帰：${e.outcome}\n` +
        `　重篤度：${e.seriousness}`,
    )
    .join("\n\n");

  return [
    "個別症例安全性報告",
    "",
    `報告ID：ICSR-BUILDER-${today.replace(/-/g, "")}`,
    "報告種別：自発報告",
    `報告日：${today}`,
    "報告者：本デモの症例ビルダーで作成（架空症例）",
    "報告者資格：不明",
    "発生国：日本",
    "MedDRAバージョン：27.0",
    "",
    "患者情報",
    `年齢：${orDash(draft.age)}`,
    `性別：${draft.sex}`,
    "",
    "被疑薬",
    `薬剤名：${drug.name}`,
    `有効成分：${drug.ingredient}`,
    `効能・効果：${drug.indication}`,
    `投与開始日：${orDash(draft.startDate)}`,
    `投与終了日：${orDash(draft.endDate)}`,
    "",
    "有害事象",
    events,
    "",
    "因果関係評価",
    `報告者による因果関係：${draft.reportedCausality}`,
    "",
    "症例経過",
    draft.narrative || "（経過の記載なし）",
    "",
  ].join("\n");
}
