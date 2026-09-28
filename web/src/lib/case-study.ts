// Narrative content for /about — the case study.
//
// Deliberately separate from the README: the README serves an engineer browsing
// the repo (architecture, ADRs, how to run), this serves someone who opened the
// demo and wants to know what problem it solves, what was decided and why, and
// what the evidence actually supports. Kept tight; depth lives in the ADRs.

// One source of truth for the supported languages.
import type { Locale } from "@/i18n/config";
export type Lang = Locale;

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
        "全ステップを同じモデルで回してはいません。経過文からの帰属判断（重篤性・因果）は難しいので高性能モデル、定型的な転記やコード化は安価なモデル。これは推測ではなく、ステップ単位で測った結果に基づいています。費用も実行ごとに実測して画面に出しており、1症例あたり約$0.03〜0.04・15〜18秒、うち費用の約85%は高性能モデルを使う2つの判定です。評価対象外の症例はゲートで止まるので$0です。",
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
    {
      title: "英語でも読めるが、モデルの出力は書き換えない",
      body:
        "英語話者にも1症例を追えるよう、画面・判定の語彙・MedDRA用語は英語化しました。一方、症例本文とモデルの判定根拠は日本語のままです。パイプラインと評価が日本語で作られており、根拠を訳せばモデル呼び出しが増えるうえ、**監査の証拠そのものを書き換える**ことになるからです。画面が「Needs review」と表示しても送る値は「要確認」であることを、テストで保証しています。",
    },
  ],

  evidenceHeading: "測った結果",
  evidenceIntro:
    "正解データ（gold）を用意し、評価ハーネスで採点しています。最重要指標は精度ではなく、過小評価がゼロであることです。3回の反復実行と、未知症例（ホールドアウト）でも確認しました。",
  metrics: [
    { value: "0", label: "過小評価（重篤度・因果・既知性）— 本評価・反復・ホールドアウトのすべてで", tone: "good" },
    { value: "100%", label: "MedDRA コード付与（単一LLMでは29%）", tone: "good" },
    { value: "83–91%", label: "重篤度一致（不一致は安全側の過大評価）", tone: "muted" },
    { value: "2/2", label: "評価対象外の症例を評価前に停止", tone: "good" },
    { value: "$0.03–0.04", label: "1症例あたりの実測費用（15〜18秒）", tone: "muted" },
    { value: "185", label: "自動テスト（バックエンド178・E2E 7）", tone: "muted" },
  ],

  limits: {
    heading: "この数字の限界",
    body: [
      "症例数はごく少なく（合成7症例、評価対象は5症例・23事象）、正解データはLLMで起案したものを、システムを作った私自身がPV実務の観点で修正した形です。**自分で作った基準に自分のシステムが一致している**部分が残るため、外部の独立した評価とは言えません。",
      "症例は合成データで、実務の報告より整っています。実際の報告は記述が乱れ、情報が欠け、書式も揃いません。実行ごとのばらつきは3回の反復で測ったのみで、信頼区間は出していません。",
      "「過去症例のフィードバックで精度が上がる」は**実証できませんでした**。未知症例では判例は何も変えず、以前見えた改善は初期データに依存したものだったと、ホールドアウトで分かりました。",
      "したがって、ここで示せているのは「精度が高い」ことではなく、**安全側の不変条件が保たれていること**と、それを測る手順があることです。",
    ],
  },

  building: {
    heading: "どう作ったか",
    body: [
      "PV実務の経験はありますが、Webフロントエンドやクラウドの実務経験はありません。この部分は**AIを使って自走して構築しました**。隠す意図はなく、むしろそこが示したい能力の一部です。",
      "ただし「動いたからよし」にはしていません。重要な判断はすべて設計判断記録（ADR）として、根拠となる再現可能な実験とセットで残しています。読めば、なぜその選択をしたかを追跡できます。",
      "自分で一行ずつ書いていないコードを信用しないための手当もしています。フロントエンドの型はバックエンドのモデルと自動で突き合わせ、ズレたらテストが落ちます。安全性の不変条件も同様にテストで固定しました。**自分の目で保証できない層は、機械で保証する**という方針です。",
      "画面も同じ考え方で、実際のブラウザでレビュアーの操作を通すテストがあります。バックエンドは本物の応答を録画して再生するので無料・決定的で、承認時に送る内容が本物のバックエンドの受理した内容と一致することを日英両方で確かめます。テストを書いたら、わざとコードを壊して**本当に失敗するか**も確認しています。",
    ],
  },

  next: {
    heading: "次にやること",
    body: [
      "独立した評価者による正解データの作成（現在の循環性を断つため）、より乱れた実務に近い症例での検証、反復回数を増やした信頼区間つきの測定。",
      "重篤性判断で唯一クラウドに依存している部分を、より大きなローカルモデルで置き換えられるかの検証。",
      "レビュー中の症例・判例を再デプロイ後も残す永続化（現在のデモではコンテナ内にあり、デプロイで消えます）。",
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
        "Not every step runs on the same model. The judgments that hinge on attributing a fact in the narrative get the stronger model; faithful transcription and coding get the cheaper one. That split came from measuring each step, not from guessing. Cost is measured on every run and shown on screen: about $0.03–0.04 and 15–18 s per case, ~85% of it the two judgments on the stronger model. An out-of-scope case stops at the gate for $0.",
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
    {
      title: "Readable in English, without rewriting what the model said",
      body:
        "So an English-speaking reader can follow a case end to end, the interface, the verdict vocabulary and MedDRA terms are in English. The case text and the model's rationales stay Japanese: the pipeline and its evaluation are Japanese, and translating the rationales would add a model call and **rewrite the audit evidence itself**. When the screen says 'Needs review', what is sent is still 要確認 — and a test proves it.",
    },
  ],

  evidenceHeading: "What the evaluation shows",
  evidenceIntro:
    "Assessments are scored against a hand-built gold set. The headline number is not accuracy — it is that under-calls are zero, which also held across 3 repeated runs and on held-out cases.",
  metrics: [
    { value: "0", label: "under-calls (seriousness / causality / expectedness) — main run, repeats and held-out", tone: "good" },
    { value: "100%", label: "MedDRA coding (a single LLM call: 29%)", tone: "good" },
    { value: "83–91%", label: "seriousness agreement (misses are safe-side over-calls)", tone: "muted" },
    { value: "2/2", label: "out-of-scope cases stopped before assessment", tone: "good" },
    { value: "$0.03–0.04", label: "measured cost per case (15–18 s)", tone: "muted" },
    { value: "185", label: "automated tests (178 backend, 7 E2E)", tone: "muted" },
  ],

  limits: {
    heading: "What these numbers do not show",
    body: [
      "The sample is small (7 synthetic cases; 5 in scope, 23 events), and the gold set was drafted with an LLM and corrected, from a PV perspective, by me — the same person who built the system. Some of the agreement is therefore **the system agreeing with its own author** — this is not an independent evaluation.",
      "The cases are synthetic and tidier than real reports, which are messy, incomplete and inconsistently formatted. Run-to-run variation was measured on only 3 runs, with no confidence intervals.",
      "'Past-case feedback improves accuracy' was **not demonstrated**. On held-out cases precedent changed nothing, and the one earlier improvement turned out to depend on seed data.",
      "So the claim being supported is not 'this is accurate'. It is that **the safe-side invariant holds**, and that there is a repeatable procedure for measuring it.",
    ],
  },

  building: {
    heading: "How it was built",
    body: [
      "My background is in pharmacovigilance, not web frontends or cloud infrastructure. Those parts were **built with AI assistance**. That is not hidden — it is part of what this project is meant to demonstrate.",
      "It is not 'it runs, so it is fine', though. Every significant decision is recorded as an architecture decision record alongside the reproducible experiment that produced its evidence, so the reasoning can be audited rather than taken on trust.",
      "And I do not trust code I did not write line by line. The frontend's types are checked automatically against the backend models, so drift fails a test; the safety invariants are pinned the same way. **Where I cannot vouch for a layer by reading it, a machine vouches for it instead.**",
      "The UI gets the same treatment: a real browser walks the reviewer's path against backend responses recorded from the real system — free and deterministic — and checks that what is sent on approval is exactly what the real backend accepted, in both languages. After writing a test, I break the code on purpose to confirm **the test actually fails**.",
    ],
  },

  next: {
    heading: "What comes next",
    body: [
      "An independently authored gold set, to break the circularity; validation on messier, more realistic reports; and more repeated runs, with confidence intervals.",
      "Testing whether a larger local model can close the one gap that still requires a cloud model — the seriousness judgment.",
      "Persisting review threads and precedent across deploys (in the demo they live in the container and reset on each deploy).",
    ],
  },

  footer:
    "All case reports and product labels used here are fictional data created for this project. No real patient information is involved.",
};

export const CASE_STUDY: Record<Lang, CaseStudy> = { ja, en };
