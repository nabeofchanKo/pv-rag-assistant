// Narrative content for /about — the case study.
//
// Deliberately separate from the README: the README serves an engineer browsing
// the repo (architecture, ADRs, how to run), this serves someone who opened the
// demo and wants to know what problem it solves, what was decided and why, and
// what the evidence actually supports. Kept tight; depth lives in the ADRs.

export type Lang = "ja" | "en";

export type Section = {
  heading: string;
  body: string[];
};

export type Decision = {
  title: string;
  body: string;
};

export type Metric = {
  value: string;
  label: string;
  tone: "good" | "muted";
};

export type CaseStudy = {
  kicker: string;
  title: string;
  lede: string;
  ctaLabel: string;
  problem: Section;
  decisionsHeading: string;
  decisionsIntro: string;
  decisions: Decision[];
  evidenceHeading: string;
  evidenceIntro: string;
  metrics: Metric[];
  limits: Section;
  building: Section;
  next: Section;
  footer: string;
};

const ja: CaseStudy = {
  kicker: "ケーススタディ",
  title: "安全性情報のトリアージを、根拠を捨てずに速くする",
  lede:
    "医薬品安全性監視（PV）の一次評価を支援するアシスタントです。有害事象報告を読み、重篤性・既知性・因果関係の評価案を出典付きで作り、人が承認します。判断を置き換えるのではなく、判断に必要な材料を整えることを目的にしています。",
  ctaLabel: "デモを触る",

  problem: {
    heading: "何が難しいのか",
    body: [
      "安全性業務では、届いた報告ひとつひとつについて「企業として重篤と評価するか」「添付文書に記載のある事象か」「因果関係を否定できるか」を判断し、該当すれば期限内に規制当局へ報告します。件数は多く、期限は短く、判断材料は非構造のテキストです。",
      "この領域には強い非対称性があります。**過大評価のコストは工数だが、過小評価のコストは報告漏れ**です。重篤かつ未知の事象を見落とせば、規制上も臨床上も実害につながります。したがって「迷ったら安全側」が設計原則になります。",
      "そして一番難しいのは、判断材料が**報告欄ではなく経過文にしかない**ケースです。「報告上は非重篤のめまい」でも、経過に「転倒して骨折、入院」と書かれていれば、企業評価は入院を根拠に重篤になります。これは定型項目の抽出では拾えません。",
    ],
  },

  decisionsHeading: "設計上の判断",
  decisionsIntro:
    "「LLMに評価させる」のではなく、LLMに何をさせないかを決めることが設計の中心でした。",
  decisions: [
    {
      title: "モデルは解釈する、決定はコードが行う",
      body:
        "LLMに「重篤かどうか」を答えさせてはいません。LLMがするのは、ICH E2A の各基準に該当する記述が本文にあるかを引用付きで挙げることだけです。そこから重篤／要確認／非重篤を決めるのは決定的なコードです。この分離のおかげで、安全性の性質を「祈る」のではなく**テストで証明**できます。実際、どんなモデル出力を与えても過小評価が起きないことを網羅的に検証しています。",
    },
    {
      title: "迷いは黙って解決せず、人に上げる",
      body:
        "確信が持てない場合の既定値を安全側に倒しています。重篤性は「要確認」、因果は「否定できない」、既知性は一致が確実でなければ「未知」扱い。要確認は非重篤に丸めず、根拠を添えてレビュー対象として浮上させます。",
    },
    {
      title: "評価してよい症例かを、評価の前に決める",
      body:
        "自社品が関与しない症例は、評価を実行せず対象外として止めます。「とりあえず評価して注記する」ではありません。企業評価は自社品スコープが前提であり、前提を満たさないものに判定を出すこと自体が誤りだからです。",
    },
    {
      title: "モデルはステップごとに選ぶ",
      body:
        "全ステップを同じモデルで回してはいません。経過文からの帰属判断（重篤性・因果）は難しいので高性能モデル、定型的な転記やコード化は安価なモデル。これは推測ではなく、ステップ単位で測った結果に基づいています。",
    },
    {
      title: "オンプレ版を測り、望まない結果を報告した",
      body:
        "機微な症例データを外に出さないローカル実行を検証しました。結果は**どのローカル7〜8Bモデルも安全性の不変条件を保てない**というもので、いずれも重篤事象を見落としました。そのため全ローカル化は見送り、転記・コード化のみローカル、臨床判断はクラウドという構成を採用しています。出したかった結論ではありませんが、測って出た結論です。",
    },
    {
      title: "人手のレビューが次の症例に効く",
      body:
        "レビュアーが「医学的に重要」と判断したコードはリストに昇格し、以後の症例で自動的に重篤と判定されます。承認された症例は判例として蓄積し、次回以降の判定と食い違えば警告します。ただし過去データは安全側にしか動かさず、単独で重篤を決めることはありません。",
    },
  ],

  evidenceHeading: "測った結果",
  evidenceIntro:
    "正解データ（gold）を用意し、評価ハーネスで採点しています。最重要指標は精度ではなく、過小評価がゼロであることです。",
  metrics: [
    { value: "0", label: "過小評価（重篤度・因果・既知性）", tone: "good" },
    { value: "100%", label: "MedDRA コード付与", tone: "good" },
    { value: "83–91%", label: "重篤度一致（不一致は安全側の過大評価）", tone: "muted" },
    { value: "165", label: "自動テスト", tone: "muted" },
  ],

  limits: {
    heading: "この数字の限界",
    body: [
      "症例数はごく少なく、正解データは自分で起案したものを後から専門的にレビューした形です。**自分で作った基準に自分のシステムが一致している**部分が残るため、外部の独立した評価とは言えません。",
      "症例は合成データで、実務の報告より整っています。実際の報告は記述が乱れ、情報が欠け、書式も揃いません。また各数値は単発実行のスナップショットで、実行ごとのばらつきは測り切れていません。",
      "したがって、ここで示せているのは「精度が高い」ことではなく、**安全側の不変条件が保たれていること**と、それを測る手順があることです。",
    ],
  },

  building: {
    heading: "どう作ったか",
    body: [
      "PV実務の経験はありますが、Webフロントエンドやクラウドの実務経験はありません。この部分は**AIを使って自走して構築しました**。隠す意図はなく、むしろそこが示したい能力の一部です。",
      "ただし「動いたからよし」にはしていません。重要な判断はすべて設計判断記録（ADR）として、根拠となる再現可能な実験とセットで残しています。読めば、なぜその選択をしたかを追跡できます。",
      "自分で一行ずつ書いていないコードを信用しないための手当もしています。フロントエンドの型はバックエンドのモデルと自動で突き合わせ、ズレたらテストが落ちます。安全性の不変条件も同様にテストで固定しました。**自分の目で保証できない層は、機械で保証する**という方針です。",
    ],
  },

  next: {
    heading: "次にやること",
    body: [
      "独立した評価者による正解データの作成（現在の循環性を断つため）、より乱れた実務に近い症例での検証、実行ごとのばらつきの測定。",
      "重篤性判断で唯一クラウドに依存している部分を、より大きなローカルモデルで置き換えられるかの検証。",
      "UIの通し自動テストと、1症例あたりのコスト・レイテンシの可視化。",
    ],
  },

  footer:
    "本プロジェクトで使用している症例・添付文書はすべて本プロジェクト用に作成した架空のデータで、実際の患者情報は含みません。",
};

const en: CaseStudy = {
  kicker: "Case study",
  title: "Making safety triage faster without throwing away the evidence",
  lede:
    "An assistant for the first-pass assessment in pharmacovigilance. It reads an adverse event report and drafts the seriousness, expectedness and causality assessments with citations, for a human to approve. The goal is not to replace the judgment but to assemble what the judgment needs.",
  ctaLabel: "Try the demo",

  problem: {
    heading: "What makes this hard",
    body: [
      "For every report that arrives, a safety team has to decide whether the company assesses it as serious, whether the reaction is already described in the product label, and whether a causal link can be ruled out — then report it to regulators within a deadline if it qualifies. The volume is high, the deadlines are short, and the evidence is unstructured text.",
      "The domain is strongly asymmetric. **An over-call costs time; an under-call is a missed report.** Failing to escalate a serious, unlabelled reaction has real regulatory and clinical consequences. That makes 'when in doubt, stay on the safe side' a design principle rather than a preference.",
      "The hardest cases are those where the deciding fact is **not in the structured fields but in the narrative**. Dizziness may be reported as non-serious, while the narrative describes a fall, a fracture and an admission — which makes the company assessment serious on the hospitalisation criterion. No amount of field extraction finds that.",
    ],
  },

  decisionsHeading: "The decisions that shaped it",
  decisionsIntro:
    "The design was driven less by what to ask the model for, and more by what not to let it decide.",
  decisions: [
    {
      title: "The model interprets, code decides",
      body:
        "The LLM is never asked whether something is serious. It is asked which ICH E2A criteria the text positively supports, with the quote. A deterministic policy turns those into serious / needs-review / non-serious. That separation is why the safety property can be **proven by test** rather than hoped for: the decision layer is checked exhaustively, so no model output can produce an under-call.",
    },
    {
      title: "Uncertainty surfaces instead of resolving quietly",
      body:
        "Defaults land on the conservative side: needs-review for seriousness, cannot-be-excluded for causality, and not-expected unless the label match is confident. A needs-review verdict is never rounded down to non-serious — it is raised to the reviewer with its evidence attached.",
    },
    {
      title: "Decide whether a case is in scope before assessing it",
      body:
        "A case with no own-company product is gated out and never assessed, rather than assessed with a caveat. Company assessment presupposes company scope, so producing verdicts for a case outside it is itself the error.",
    },
    {
      title: "Choose the model per step",
      body:
        "Not every step runs on the same model. The judgments that hinge on attributing a fact in the narrative get the stronger model; faithful transcription and coding get the cheaper one. That split came from measuring each step, not from guessing.",
    },
    {
      title: "Measured the on-premise option and reported the result I did not want",
      body:
        "Running locally would keep sensitive case text off third-party APIs, so it was benchmarked properly. The finding: **no local 7–8B model preserved the safety invariant** — every one missed a serious event. So the fully-local tier was not shipped. What shipped is a split: transcription and coding run locally, the clinical judgments stay on the frontier model.",
    },
    {
      title: "Human review feeds the next case",
      body:
        "A code the reviewer judges medically important is promoted to a list, so later cases coded to it are flagged serious automatically. Approved cases accumulate as precedent and raise a warning when a new draft disagrees with them. Past data may only move a verdict toward the safe side, and never decides 'serious' on its own.",
    },
  ],

  evidenceHeading: "What the evaluation shows",
  evidenceIntro:
    "Assessments are scored against a hand-built gold set. The headline number is not accuracy — it is that under-calls are zero.",
  metrics: [
    { value: "0", label: "under-calls (seriousness / causality / expectedness)", tone: "good" },
    { value: "100%", label: "MedDRA coding", tone: "good" },
    { value: "83–91%", label: "seriousness agreement (misses are safe-side over-calls)", tone: "muted" },
    { value: "165", label: "automated tests", tone: "muted" },
  ],

  limits: {
    heading: "What these numbers do not show",
    body: [
      "The sample is small, and the gold set was drafted by the same person who built the system before being reviewed. Some of the agreement is therefore **the system agreeing with its own author** — this is not an independent evaluation.",
      "The cases are synthetic and tidier than real reports, which are messy, incomplete and inconsistently formatted. The figures are also single-run snapshots, so run-to-run variation is not captured.",
      "So the claim being supported is not 'this is accurate'. It is that **the safe-side invariant holds**, and that there is a repeatable procedure for measuring it.",
    ],
  },

  building: {
    heading: "How it was built",
    body: [
      "My background is in pharmacovigilance, not web frontends or cloud infrastructure. Those parts were **built with AI assistance**. That is not hidden — it is part of what this project is meant to demonstrate.",
      "It is not 'it runs, so it is fine', though. Every significant decision is recorded as an architecture decision record alongside the reproducible experiment that produced its evidence, so the reasoning can be audited rather than taken on trust.",
      "And I do not trust code I did not write line by line. The frontend's types are checked automatically against the backend models, so drift fails a test; the safety invariants are pinned the same way. **Where I cannot vouch for a layer by reading it, a machine vouches for it instead.**",
    ],
  },

  next: {
    heading: "What comes next",
    body: [
      "An independently authored gold set, to break the circularity; validation on messier, more realistic reports; and measuring run-to-run variation.",
      "Testing whether a larger local model can close the one gap that still requires a cloud model — the seriousness judgment.",
      "An end-to-end UI test, and surfacing cost and latency per case.",
    ],
  },

  footer:
    "All case reports and product labels used here are fictional data created for this project. No real patient information is involved.",
};

export const CASE_STUDY: Record<Lang, CaseStudy> = { ja, en };
