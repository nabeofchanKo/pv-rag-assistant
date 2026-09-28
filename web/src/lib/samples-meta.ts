// What each bundled sample case is FOR.
//
// These are not arbitrary demo files — each one was written to probe a specific
// behaviour of the triage pipeline, and the expected outcome is fixed in
// data/gold/*.gold.json (the evaluation harness scores against it). Surfacing
// the intent turns the demo from "it runs" into "here is what it is tested to do".
//
// Pure data, no node APIs, so it is safe to import from anywhere.

export type SampleMeta = {
  file: string;
  label: string;
  caseId: string;
  drug: string;
  /** Short line shown on the run buttons. */
  hint: string;
  /** One-line positioning. */
  role: string;
  inScope: boolean;
  /** What this case is designed to catch. */
  probes: { title: string; detail: string }[];
  /** The fixed expectation from the gold set. */
  expected: string;
};

export const SAMPLE_META: SampleMeta[] = [
  {
    file: "case_001.txt",
    label: "症例001",
    caseId: "ICSR-2025-001",
    drug: "DrugX",
    hint: "DrugX / 頭痛ほか",
    role: "基準ケース — 基本動作の確認",
    inScope: true,
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
  {
    file: "case_003.txt",
    label: "症例003",
    caseId: "ICSR-2025-003",
    drug: "DrugZ",
    hint: "DrugZ / 多数事象・最難関",
    role: "最難関 — 経過文からの帰属判断",
    inScope: true,
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
        detail:
          "QTc間隔の延長は「重大な副作用」に該当し、重篤かつ既知。",
      },
    ],
    expected:
      "9事象。重篤＝徐脈（症候性）・失神・QTc間隔の延長。起立性低血圧と錯乱状態は 非重篤かつ未知。因果はすべて 否定できない。",
  },
  {
    file: "case_004.txt",
    label: "症例004",
    caseId: "ICSR-2025-004",
    drug: "DrugA（自社品ではない）",
    hint: "他社品 / 評価対象外",
    role: "ハードゲート — 評価してはいけない症例",
    inScope: false,
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
];

export const SAMPLE_FILES = SAMPLE_META.map((s) => s.file);
