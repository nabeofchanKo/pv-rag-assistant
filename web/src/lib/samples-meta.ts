import type { Locale } from "@/i18n/config";

// What each bundled sample case is FOR.
//
// These are not arbitrary demo files — each one was written to probe a specific
// behaviour of the triage pipeline, and the expected outcome is fixed in
// data/gold/*.gold.json (the evaluation harness scores against it). Surfacing
// the intent turns the demo from "it runs" into "here is what it is tested to do".
//
// The case files themselves are Japanese (that is what the pipeline reads);
// public/samples/en/ holds English reference translations for readers, never
// sent to the backend (lib/demo.ts only allows the file names below).
//
// Pure data, no node APIs, so it is safe to import from anywhere.

export type SampleText = {
  label: string;
  drug: string;
  /** Short line shown on the run buttons. */
  hint: string;
  /** One-line positioning. */
  role: string;
  /** What this case is designed to catch. */
  probes: { title: string; detail: string }[];
  /** The fixed expectation from the gold set. */
  expected: string;
};

export type SampleMeta = {
  file: string;
  caseId: string;
  inScope: boolean;
  text: Record<Locale, SampleText>;
};

export const SAMPLE_META: SampleMeta[] = [
  {
    file: "case_001.txt",
    caseId: "ICSR-2025-001",
    inScope: true,
    text: {
      ja: {
        label: "症例001",
        drug: "DrugX",
        hint: "DrugX / 頭痛ほか",
        role: "基準ケース — 基本動作の確認",
        probes: [
          {
            title: "重症度と重篤性を混同しないか",
            detail:
              "「頭痛（重度）」は症状としては重いが、ICH E2A の重篤性基準（死亡・生命を脅かす・入院／入院期間の延長・障害・先天異常・医学的に重要）のいずれにも該当しない。severity が高いことを理由に重篤と判定してしまう誤りを検出する。",
          },
          {
            title: "添付文書にある事象／ない事象を分けられるか",
            detail:
              "頭痛・浮動性めまいは DrugX 添付文書の「その他の副作用」に記載があり既知。悪心は記載がなく未知。記載のない事象を既知と読み込むと、未知の副作用の報告漏れにつながる。",
          },
          {
            title: "投与中の事象の因果を保守的に置けるか",
            detail:
              "投与開始後に発現した事象は、トリアージ段階では因果を「否定できない」に留める。安易に否定するとスコープから外れてしまう。",
          },
        ],
        expected:
          "3事象すべて 非重篤／否定できない。既知＝頭痛・浮動性めまい、未知＝悪心。",
      },
      en: {
        label: "Case 001",
        drug: "DrugX",
        hint: "DrugX / headache and more",
        role: "Baseline — does the basic flow work",
        probes: [
          {
            title: "Does it keep severity and seriousness apart?",
            detail:
              "“Headache (severe)” is a severe symptom, but meets none of the ICH E2A seriousness criteria (death, life-threatening, hospitalization, disability, congenital anomaly, medically important). Catches the error of calling an event serious because it is severe.",
          },
          {
            title: "Can it tell labelled from unlabelled events?",
            detail:
              "Headache and dizziness are listed under “other adverse reactions” in the DrugX package insert, so expected; nausea is not listed, so unexpected. Reading an unlisted event as expected leads to a missed report of an unexpected reaction.",
          },
          {
            title: "Does it keep causality conservative for events on treatment?",
            detail:
              "For events that start after dosing begins, triage leaves causality at “cannot be ruled out”. Ruling it out too readily drops the case from scope.",
          },
        ],
        expected:
          "All 3 events non-serious / causality cannot be ruled out. Expected: headache, dizziness; unexpected: nausea.",
      },
    },
  },
  {
    file: "case_003.txt",
    caseId: "ICSR-2025-003",
    inScope: true,
    text: {
      ja: {
        label: "症例003",
        drug: "DrugZ",
        hint: "DrugZ / 多数事象・最難関",
        role: "最難関 — 経過文からの帰属判断",
        probes: [
          {
            title: "入院の原因をどの事象に帰属するか（最重要）",
            detail:
              "入院の原因は徐脈（症候性）と失神であり、この2つが重篤。一方、経過文には「入院中に軽度の起立性低血圧を認めたが、退院時までに消失した」とある。これは入院の原因ではないため非重篤。近くに「入院」の語があるだけで周辺事象まで重篤にしてしまう“もらい火”を検出する。ローカルLLMの比較検証では、どのモデルもこの帰属で失敗した。",
          },
          {
            title: "投与中止後の事象で因果を早まって否定しないか",
            detail:
              "錯乱状態は DrugZ 中止から3週間後に発現しており、時間的には非典型。しかし DrugZ は活性代謝物の半減期が長く、遅発性の中枢神経系への影響を否定できない。「中止後だから無関係」と切り捨てないかを見る。",
          },
          {
            title: "相互作用欄の記載も既知と認めるか",
            detail:
              "INR増加・鼻出血・斑状出血は、ワルファリン併用時の相互作用として添付文書に記載がある。副作用欄だけを見ていると未知と誤判定する。",
          },
          {
            title: "重大な副作用を取りこぼさないか",
            detail: "QTc間隔の延長は「重大な副作用」に該当し、重篤かつ既知。",
          },
        ],
        expected:
          "9事象。重篤＝徐脈（症候性）・失神・QTc間隔の延長。起立性低血圧と錯乱状態は 非重篤かつ未知。因果はすべて 否定できない。",
      },
      en: {
        label: "Case 003",
        drug: "DrugZ",
        hint: "DrugZ / many events, hardest",
        role: "Hardest — attributing seriousness from the narrative",
        probes: [
          {
            title: "Which event caused the hospitalization? (most important)",
            detail:
              "The admission was caused by symptomatic bradycardia and syncope, so those two are serious. The narrative also says “mild orthostatic hypotension was noted during the admission and had resolved by discharge” — that did not cause the admission, so it is non-serious. Catches “contagion”, where an event becomes serious just because the word hospitalization is nearby. In the local-LLM comparison, every model failed this attribution.",
          },
          {
            title: "Does it avoid ruling out causality too early after the drug is stopped?",
            detail:
              "The confusional state began three weeks after DrugZ was stopped — temporally atypical. But DrugZ's active metabolite has a long half-life, so a delayed CNS effect cannot be ruled out. Checks that “it started after stopping, so it is unrelated” is not the conclusion.",
          },
          {
            title: "Does it count the interactions section as labelled?",
            detail:
              "INR increased, epistaxis and ecchymosis are in the package insert as an interaction with warfarin. Looking only at the adverse-reactions section would wrongly call them unexpected.",
          },
          {
            title: "Does it catch a clinically significant adverse reaction?",
            detail:
              "QTc prolongation is listed under “clinically significant adverse reactions”: serious and expected. It appears only in the narrative, not in the event list.",
          },
        ],
        expected:
          "9 events. Serious: symptomatic bradycardia, syncope, QTc prolongation. Orthostatic hypotension and confusional state: non-serious and unexpected. Causality cannot be ruled out for all.",
      },
    },
  },
  {
    file: "case_004.txt",
    caseId: "ICSR-2025-004",
    inScope: false,
    text: {
      ja: {
        label: "症例004",
        drug: "DrugA（自社品ではない）",
        hint: "他社品 / 評価対象外",
        role: "ハードゲート — 評価してはいけない症例",
        probes: [
          {
            title: "自社品が無いとき、評価を実行せずに止まれるか",
            detail:
              "被疑薬 DrugA は自社製品マスタに存在しない。企業としての安全性評価は「自社品が関与していること」が前提なので、抽出も4判定も走らせてはならない。この症例からは有害事象が7つ読み取れてしまうため、“読めるからやってしまう”挙動を検出できる。",
          },
          {
            title: "曖昧な消費者報告でもゲートが効くか",
            detail:
              "報告者は患者の配偶者（非医療従事者）で、記述は口語的かつ薬剤名も一部不明。入力が曖昧でもスコープ判定が崩れないかを見る。",
          },
        ],
        expected:
          "out_of_scope（評価対象外）として即終了。抽出・MedDRA・重篤度・既知/未知・因果はいずれも実行されない。",
      },
      en: {
        label: "Case 004",
        drug: "DrugA (not an own-company product)",
        hint: "other company's drug / out of scope",
        role: "Hard gate — a case that must not be assessed",
        probes: [
          {
            title: "Does it stop without assessing when no own product is involved?",
            detail:
              "The suspect drug DrugA is not in the company product master. A company safety assessment presupposes that one of its own products is involved, so neither extraction nor the four judgments may run. Seven adverse events can be read from this case, which is what exposes a “it's readable, so do it” behaviour.",
          },
          {
            title: "Does the gate hold for a vague consumer report?",
            detail:
              "The reporter is the patient's spouse (not a healthcare professional); the account is colloquial and one drug name is unknown. Checks that the scope decision survives ambiguous input.",
          },
        ],
        expected:
          "Ends immediately as out_of_scope. Extraction, MedDRA, seriousness, expectedness and causality are not run.",
      },
    },
  },
];

export const SAMPLE_FILES = SAMPLE_META.map((s) => s.file);

/** Localized text for a sample, by file name (undefined for a non-sample). */
export function sampleText(file: string, locale: Locale): SampleText | undefined {
  return SAMPLE_META.find((s) => s.file === file)?.text[locale];
}
