import type { KnownValue } from "@/lib/labels";

// Japanese UI strings — the source of truth for the dictionary's SHAPE.
// en.ts is typed as `Dictionary`, so a key added here and not translated there
// (or misspelled there) fails the type check instead of rendering `undefined`.
//
// Values are plain strings, or small functions where a value is interpolated.

export const ja = {
  meta: {
    description:
      "医薬品安全性監視（PV）のトリアージ・一次評価支援。すべての回答を出典に紐づけます。",
  },
  nav: {
    triage: "症例トリアージ",
    rag: "RAG Q&A",
    samples: "サンプル症例",
    about: "このプロジェクトについて",
    languageLabel: "表示言語",
  },

  // How API values are displayed. Japanese shows the value itself, so `values`
  // is empty here; en.ts must cover every KnownValue.
  vocab: {
    values: {} as Partial<Record<KnownValue, string>>,
    axis: { seriousness: "重篤度", causality: "因果関係", expectedness: "既知/未知" },
    aeSource: { reported: "報告済み", narrative: "経過から読取り" },
    influenceSource: { IME: "以前のFB(IME)", precedent: "過去症例" },
    changeSource: { reviewer: "人手レビュー", IME: "以前のFB(IME)", precedent: "過去症例" },
    editKind: { removed: "削除", added: "追加", recoded: "PT修正" },
    step: {
      product_match: "自社品判定",
      out_of_scope: "評価対象外ゲート",
      extraction: "有害事象の抽出",
      meddra: "MedDRAコード化",
      seriousness: "重篤度",
      causality: "因果関係",
      expectedness: "既知/未知",
      precedent: "過去症例の参照",
      influence: "過去データの反映",
    },
    listSep: "、",
    countSep: "／",
    countItem: (label: string, n: number) => `${label}${n}`,
    dateLocale: "ja-JP",
    paren: (s: string) => `（${s}）`,
  },

  triage: {
    kicker: "症例トリアージ",
    title: "症例を一次評価する",
    intro:
      "症例報告（PDF / テキスト / メール / 画像）を投入すると、自社品判定 → 有害事象抽出 → MedDRAコード → 重篤度・既知/未知・因果 → 過去判例の順に、出典付きの評価ドラフトを生成します。",
    // Shown only in English: what stays Japanese, and why.
    languageNote: "",
    chooseFile: "ファイルを選択",
    fileHint: "PDF / .txt / .eml / 画像",
    run: "トリアージ実行",
    modeSample: "サンプル症例",
    modeBuild: "症例を作る",
    trySample: "サンプル症例で試す",
    demoNote:
      "公開デモのため、実行は同梱のサンプル症例に限定し、回数にも制限を設けています。",
    running: "解析中… 6ステップ評価（抽出 → MedDRA → 重篤度 → 既知/未知 → 因果 → 判例）",
    failed: (status: number) => `トリアージ失敗 (HTTP ${status})`,
    oosKicker: "out of scope · 評価対象外",
    oosTitle: "自社品が使用されていないため、評価は実行されません",
    oosGate:
      "自社品判定を前提条件とするハードゲート（Phase 4g）により、抽出・MedDRA・4判定は実行されていません。",
    sourceText: "読み取ったテキスト（出典）",
    status: {
      awaiting_review: "awaiting_review · レビュー待ち",
      approved: "approved · 承認済み",
      rejected: "rejected · 却下",
    },
    escalations: (n: number) => `⚠️ レビュー要注意（安全側の不確実バンド）— ${n}件`,
  },

  sections: {
    summary: "判定サマリー",
    companyProduct: (names: string) => `自社品 ${names}`,
    noCompanyProduct: "自社品なし",
    stats: {
      events: "有害事象",
      serious: "重篤",
      check: "要確認",
      unexpected: "未知",
      notExcludable: "因果 否定できない",
    },
    flagged: (n: number) => `重篤かつ既知でない事象が ${n} 件 — 迅速報告の検討対象`,
    flaggedNote: "ドラフト作成の補助であり、報告要否の判断そのものではありません。",
    changesTitle: (n: number) => `人手・過去データによる調整 — ${n} 件`,
    changesNote:
      "モデルが最初に出した判定と、そこから変わった判定を並べています。過去データ由来の変化は 1 回の実行結果から復元しているため、モデルの実行ごとのばらつきは混ざりません。",
    changesHead: ["事象", "軸", "モデルの判定", "調整後", "由来", "理由"],
    changedVia: "から",
    byReviewer: "人手",
    byPastData: "過去データ",
    eventsTitle: "事象一覧",
    eventsHint: "行を開くと根拠が表示されます",
    cols: {
      event: "事象",
      pt: "MedDRA PT",
      seriousness: "重篤度",
      causality: "因果",
      expectedness: "既知/未知",
    },
    source: "出典",
    reviewerAdded: "レビュアー追加",
    onset: "発現日",
    outcome: "転帰",
    reportedSeriousness: "報告重篤度",
    codedBy: "コード由来",
    serTitle: "重篤度（企業評価 / ICH E2A）",
    reportedDiffers: (reported: string) => `⚠️ 報告（${reported}）と差異`,
    criteria: "該当基準",
    cauTitle: "因果関係（時間的・保守的）",
    expTitle: (drug: string) => `既知/未知 — ${drug}`,
    match: "一致",
    precedentTitle: (n: number) => `過去症例（同一PT ${n} 件）`,
    conflicts: "⚠️ 不一致",
    refs: "参照",
    patientTitle: "患者・自社品の詳細",
    age: "年齢",
    sex: "性別",
    hitTerm: "ヒット語",
    noProduct: "自社品の該当なし。",
    influenceTitle: "過去データの扱い",
    influenceMode: { applied: "反映", advisory: "参考" },
    influenceNone:
      "今回、過去データ（IME・過去症例）による調整や参考情報はありませんでした。",
    influenceHead: ["事象", "軸", "由来"],
    influenceChange: "変更",
    influenceMemo: "メモ",
  },

  review: {
    title: "レビュー・承認（HITL）",
    errFallback: (status: number) => `確定に失敗しました (HTTP ${status})`,
    reviewerRequired: "レビュー担当者名は必須です。",
    escalationsNote: (n: number) =>
      `安全側で『要確認 / 評価不能』の項目が ${n} 件あります。判断のうえ承認してください。`,
    noEscalations: "安全側の要確認項目はありません。内容を確認して承認してください。",
    reviewerLabel: "レビュー担当者名",
    required: "*必須",
    reviewerPlaceholder: "例：田中PV担当",
    noteLabel: "全体所見（任意）",
    notePlaceholder: "所見があれば記入",
    overrideTitle: "判定の上書き（任意）",
    overrideNote:
      "「変更後」を変えた項目だけが上書きされます。元の判定は監査証跡として保持されます。",
    overrideHead: ["事象", "現在", "変更後", "変更理由"],
    newVerdictLabel: (axis: string, term: string) => `${axis} ${term} の変更後`,
    rationaleLabel: (axis: string, term: string) => `${axis} ${term} の変更理由`,
    rationalePlaceholder: "変更理由（任意）",
    imeTitle: "IMEリストへの昇格（任意）",
    imeNote:
      "「医学的に重要」と判断したPTを追加すると、今後の症例で同じPTの事象が自動的に重篤（criterion 6）になります。",
    imeHead: ["IMEに追加", "事象", "PT名", "PTコード", "昇格理由"],
    imeAddLabel: (pt: string) => `${pt} をIMEに追加`,
    imeRationaleLabel: (pt: string) => `${pt} の昇格理由`,
    imeRationalePlaceholder: "昇格理由（任意）",
    editTitle: "抽出の修正（任意）",
    editNote: "誤抽出は「削除」にチェック。MedDRAが違う場合は PTコード / PT名 を直接修正。",
    editHead: ["削除", "事象", "PTコード", "PT名"],
    removeLabel: (term: string) => `${term} を削除`,
    ptCodeLabel: (term: string) => `${term} のPTコード`,
    ptNameLabel: (term: string) => `${term} のPT名`,
    addNote: "見落とし事象を追加（判定は手入力。安全側の既定値が入っています）。",
    addHead: ["事象", "PTコード", "PT名", "重篤度", "因果", ""],
    addedLabel: (i: number, field: string) => `追加事象 ${i} の${field}`,
    addedFields: { name: "名称", ptCode: "PTコード", ptName: "PT名", ser: "重篤度", cau: "因果" },
    addedRemove: (i: number) => `追加事象 ${i} を削除`,
    termPlaceholder: "事象名",
    addButton: "＋ 事象を追加",
    approve: "承認する",
    reject: "却下する",
    approvedBanner: "✅ 承認済み",
    rejectedBanner: "⛔ 却下",
    by: (reviewer: string, when: string) => ` — 担当: ${reviewer} / ${when}`,
    note: (note: string) => `所見: ${note}`,
    overridesTitle: "人手による上書き（監査証跡）",
    noOverrides: "上書きなし（ドラフトのまま確定）。",
    overridesHead: ["軸", "事象", "製品", "元の判定", "変更後", "理由"],
    editsTitle: "抽出の修正（監査証跡）",
    editsHead: ["種別", "事象", "詳細"],
    imePromotedTitle: "IMEリストへ昇格したPT（今後の症例に反映）",
    imePromotedHead: ["PT名", "PTコード", "状態", "理由"],
    reset: "別の症例をレビューする",
  },

  telemetry: {
    title: "コスト・処理時間",
    unpricedSuffix: "＋未登録分",
    head: ["ステップ", "モデル", "タイムライン", "時間", "入力 / 出力", "費用"],
    noLlm: "—（LLMなし）",
    total: "合計（待ち時間）",
    unpriced: "価格未登録",
    sec: (ms: number) => `${(ms / 1000).toFixed(1)}秒`,
    barTitle: (start: string, dur: string) => `開始 +${start} ／ ${dur}`,
    measured: (asOf: string) =>
      `この実行で実測した値です（推定ではありません）。価格は ${asOf} 時点の OpenAI 標準料金で計算しています。`,
    parallel: (sum: string, wall: string) =>
      `既知/未知・因果関係・MedDRA は並列に実行されるため、各ステップの時間の合計（${sum}）は実際の待ち時間（${wall}）より長くなります。`,
    cached: (pct: number) =>
      `入力の ${pct}% はプロンプトキャッシュに一致し、割引単価で課金されています。同じ症例を初めて実行するときは、この割合が下がり費用は上がります。`,
    unpricedNote: "価格表にないモデル（ローカルモデル等）の分は合計に含まれていません。",
    embeddings: "検索用の埋め込み（添付文書・MedDRA）は含みません。この規模では 1 セント未満です。",
  },
};

export type Dictionary = typeof ja;
