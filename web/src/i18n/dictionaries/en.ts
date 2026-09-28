import type { KnownValue } from "@/lib/labels";
import type { Dictionary } from "./ja";

// English UI strings. Must match ja.ts key for key (enforced by the type).

// Every Japanese value the API can send, as shown in English. Typed as a full
// Record, so a value added to lib/labels.ts without a translation here fails
// the type check. (Several lists share a value — 不明, 死亡, 該当なし, 要確認,
// 評価不能 — and one translation serves all of them.)
const VALUES: Record<KnownValue, string> = {
  // verdicts
  重篤: "Serious",
  非重篤: "Non-serious",
  要確認: "Needs review",
  否定できない: "Cannot be ruled out",
  否定できる: "Can be ruled out",
  評価不能: "Unassessable",
  既知: "Expected",
  未知: "Unexpected",
  判定不能: "Undeterminable",
  // ICH E2A seriousness criteria
  死亡: "Death",
  生命を脅かす: "Life-threatening",
  "入院・入院期間の延長": "Hospitalization (initial or prolonged)",
  障害: "Disability",
  先天異常: "Congenital anomaly",
  医学的に重要: "Medically important",
  // MedDRA coding route
  完全一致: "Exact match",
  "検索+LLM": "Retrieval + LLM",
  該当なし: "No match",
  手動: "Manual",
  // label match type (expectedness evidence)
  直接一致: "Direct match",
  同義語: "Synonym",
  "読み替え・類似": "Paraphrase / similar",
  "機序・文脈のみ": "Mechanism / context only",
  // onset relative to dosing
  投与開始前: "Before dosing",
  投与中: "During treatment",
  投与中止後: "After discontinuation",
  不明: "Unknown",
  // patient
  女性: "Female",
  男性: "Male",
  // outcome
  軽快: "Improving",
  回復: "Recovered",
  未回復: "Not recovered",
  後遺症あり: "Recovered with sequelae",
  // reporter's causality (case builder)
  "可能性あり（Possible）": "Possible",
  "関連あり（Probable）": "Probable",
  "関連なし（Unlikely）": "Unlikely",
  // IME promotion status, criterion source
  追加: "Added",
  既存: "Already listed",
  症例記述: "Case narrative",
  IME: "IME list",
};

export const en: Dictionary = {
  meta: {
    description:
      "Pharmacovigilance (PV) case triage and first-pass assessment. Every answer is tied to its source.",
  },
  nav: {
    triage: "Case triage",
    rag: "RAG Q&A",
    samples: "Sample cases",
    about: "About",
    languageLabel: "Language",
  },

  vocab: {
    values: VALUES,
    axis: { seriousness: "Seriousness", causality: "Causality", expectedness: "Expectedness" },
    aeSource: { reported: "Reported", narrative: "Read from narrative" },
    influenceSource: { IME: "Earlier feedback (IME)", precedent: "Past cases" },
    changeSource: { reviewer: "Reviewer", IME: "Earlier feedback (IME)", precedent: "Past cases" },
    editKind: { removed: "Removed", added: "Added", recoded: "PT corrected" },
    step: {
      product_match: "Own-product check",
      out_of_scope: "Out-of-scope gate",
      extraction: "Event extraction",
      meddra: "MedDRA coding",
      seriousness: "Seriousness",
      causality: "Causality",
      expectedness: "Expectedness",
      precedent: "Past-case lookup",
      influence: "Past-data adjustment",
    },
    listSep: ", ",
    countSep: " / ",
    countItem: (label: string, n: number) => `${label} ${n}`,
    dateLocale: "en-US",
    paren: (s: string) => ` (${s})`,
  },

  triage: {
    kicker: "Case triage",
    title: "First-pass assessment of a case",
    intro:
      "Submit an adverse event report (PDF / text / email / image) and it drafts a sourced assessment in order: own-product check → event extraction → MedDRA coding → seriousness, expectedness and causality → past-case precedent.",
    languageNote:
      "The UI is in English; the case reports, the Japanese package inserts they are checked against, and the model's free-text rationales are in Japanese — the pipeline and its evaluation are built for Japanese PV. Verdicts, criteria and MedDRA terms are shown in English.",
    chooseFile: "Choose file",
    fileHint: "PDF / .txt / .eml / image",
    run: "Run triage",
    modeSample: "Sample cases",
    modeBuild: "Build a case",
    trySample: "Try a sample case",
    demoNote:
      "As a public demo, runs are limited to the bundled sample cases and rate limited.",
    running:
      "Analyzing… six-step assessment (extraction → MedDRA → seriousness → expectedness → causality → precedent)",
    failed: (status: number) => `Triage failed (HTTP ${status})`,
    oosKicker: "out of scope",
    oosTitle: "No own-company product is involved, so no assessment is run",
    oosGate:
      "A hard gate makes the own-product check a precondition (Phase 4g): extraction, MedDRA coding and the four judgments were not run.",
    sourceText: "Text as read (source)",
    referenceTranslation: "English reference translation",
    referenceTranslationNote:
      "For reading only — the pipeline reads the Japanese original above, not this text.",
    status: {
      awaiting_review: "awaiting_review · Awaiting review",
      approved: "approved · Approved",
      rejected: "rejected · Rejected",
    },
    escalations: (n: number) => `⚠️ Needs attention (safety-side uncertainty band) — ${n}`,
  },

  sections: {
    summary: "Summary",
    companyProduct: (names: string) => `Own product: ${names}`,
    noCompanyProduct: "No own product",
    stats: {
      events: "Adverse events",
      serious: "Serious",
      check: "Needs review",
      unexpected: "Unexpected",
      notExcludable: "Causality not ruled out",
    },
    flagged: (n: number) =>
      `${n} serious event${n === 1 ? "" : "s"} not in the label — candidate${n === 1 ? "" : "s"} for expedited reporting`,
    flaggedNote: "An aid for drafting, not the reporting decision itself.",
    changesTitle: (n: number) => `Adjusted by the reviewer or past data — ${n}`,
    changesNote:
      "The model's first verdict next to where it ended up. Past-data changes are reconstructed from a single run, so run-to-run model variation does not leak in.",
    changesHead: ["Event", "Axis", "Model's verdict", "Adjusted", "Source", "Reason"],
    changedVia: "·",
    byReviewer: "reviewer",
    byPastData: "past data",
    eventsTitle: "Adverse events",
    eventsHint: "Open a row for the evidence",
    cols: {
      event: "Event",
      pt: "MedDRA PT",
      seriousness: "Seriousness",
      causality: "Causality",
      expectedness: "Expectedness",
    },
    source: "Source",
    reviewerAdded: "Added by reviewer",
    onset: "Onset",
    outcome: "Outcome",
    reportedSeriousness: "Reported seriousness",
    codedBy: "Coded by",
    serTitle: "Seriousness (company assessment / ICH E2A)",
    reportedDiffers: (reported: string) => `⚠️ Differs from the report (${reported})`,
    criteria: "Criteria met",
    cauTitle: "Causality (temporal, conservative)",
    expTitle: (drug: string) => `Expectedness — ${drug}`,
    match: "Match",
    precedentTitle: (n: number) => `Past cases (same PT, ${n})`,
    conflicts: "⚠️ Disagrees on",
    refs: "Cases",
    patientTitle: "Patient and own-product details",
    age: "Age",
    sex: "Sex",
    hitTerm: "matched on",
    noProduct: "No own product found.",
    influenceTitle: "Use of past data",
    influenceMode: { applied: "applied", advisory: "advisory" },
    influenceNone: "No adjustments or notes from past data (IME list, past cases) this time.",
    influenceHead: ["Event", "Axis", "Source"],
    influenceChange: "Change",
    influenceMemo: "Note",
  },

  review: {
    title: "Review and approval (HITL)",
    errFallback: (status: number) => `Could not finalize (HTTP ${status})`,
    reviewerRequired: "Reviewer name is required.",
    escalationsNote: (n: number) =>
      `${n} item${n === 1 ? " was" : "s were"} left at "needs review / unassessable" on the safe side. Decide, then approve.`,
    noEscalations: "No safety-side items need review. Check the draft and approve.",
    reviewerLabel: "Reviewer name",
    required: "*required",
    reviewerPlaceholder: "e.g. Tanaka, PV",
    noteLabel: "Overall note (optional)",
    notePlaceholder: "Any observations",
    overrideTitle: "Override verdicts (optional)",
    overrideNote:
      "Only rows where you change the new verdict are overridden. The original verdict is kept in the audit trail.",
    overrideHead: ["Event", "Current", "New verdict", "Reason"],
    newVerdictLabel: (axis: string, term: string) => `${axis} ${term}: new verdict`,
    rationaleLabel: (axis: string, term: string) => `${axis} ${term}: reason`,
    rationalePlaceholder: "Reason (optional)",
    imeTitle: "Promote to the IME list (optional)",
    imeNote:
      "Adding a PT you judge medically important makes future events coded to it serious automatically (criterion 6).",
    imeHead: ["Add to IME", "Event", "PT name", "PT code", "Reason"],
    imeAddLabel: (pt: string) => `Add ${pt} to the IME list`,
    imeRationaleLabel: (pt: string) => `Reason for promoting ${pt}`,
    imeRationalePlaceholder: "Reason (optional)",
    editTitle: "Correct the extraction (optional)",
    editNote:
      "Tick “Remove” for a wrongly extracted event. If the MedDRA coding is wrong, edit the PT code / name directly.",
    editHead: ["Remove", "Event", "PT code", "PT name"],
    removeLabel: (term: string) => `Remove ${term}`,
    ptCodeLabel: (term: string) => `PT code for ${term}`,
    ptNameLabel: (term: string) => `PT name for ${term}`,
    addNote: "Add a missed event (verdicts entered by hand; safe-side defaults are pre-filled).",
    addHead: ["Event", "PT code", "PT name", "Seriousness", "Causality", ""],
    addedLabel: (i: number, field: string) => `Added event ${i}: ${field}`,
    addedFields: { name: "name", ptCode: "PT code", ptName: "PT name", ser: "seriousness", cau: "causality" },
    addedRemove: (i: number) => `Remove added event ${i}`,
    termPlaceholder: "Event term",
    addButton: "+ Add event",
    approve: "Approve",
    reject: "Reject",
    approvedBanner: "✅ Approved",
    rejectedBanner: "⛔ Rejected",
    by: (reviewer: string, when: string) => ` — by ${reviewer} / ${when}`,
    note: (note: string) => `Note: ${note}`,
    overridesTitle: "Reviewer overrides (audit trail)",
    noOverrides: "No overrides (finalized as drafted).",
    overridesHead: ["Axis", "Event", "Product", "Original", "New", "Reason"],
    editsTitle: "Extraction corrections (audit trail)",
    editsHead: ["Kind", "Event", "Detail"],
    imePromotedTitle: "PTs promoted to the IME list (applies to future cases)",
    imePromotedHead: ["PT name", "PT code", "Status", "Reason"],
    reset: "Review another case",
  },

  builder: {
    intro:
      "Compose a report and narrative to see how the assessment responds. For example: dizziness reported as non-serious, but the narrative describes a fall, a fracture and admission — does the company assessment upgrade it to serious on the hospitalization criterion?",
    inputNote:
      "Enter event terms and the narrative in Japanese: the pipeline (extraction, MedDRA retrieval, package-insert matching) is built and evaluated for Japanese reports. “Load the example” fills in the case described above; its English rendering is shown under the narrative.",
    loadExample: "Load the example",
    drug: "Suspect drug",
    notOwn: " (not an own product)",
    age: "Age",
    agePlaceholder: "e.g. 78歳",
    sex: "Sex",
    startDate: "Start date",
    endDate: "Stop date",
    reportedCausality: "Reporter's causality",
    notOwnWarning:
      "This drug is not in the company product master, so no assessment runs and the case ends as out of scope (to check the hard gate).",
    eventsTitle: "Reported adverse events",
    eventsNote:
      "Transcribed as reported. The company assessment (seriousness, causality, expectedness) is made by the system from these together with the narrative.",
    eventLabel: (i: number, field: string) => `Event ${i}: ${field}`,
    eventFields: { name: "term", onset: "onset", outcome: "outcome", ser: "reported seriousness" },
    eventRemove: (i: number) => `Remove event ${i}`,
    termPlaceholder: "Event term (e.g. 浮動性めまい)",
    onsetPlaceholder: "Onset",
    addEvent: "+ Add event",
    narrativeTitle: "Narrative",
    narrativeNote:
      "This is where the judgment is won or lost. Put facts in the narrative that the event fields do not mention (a fall, a fracture, admission, a procedure) and see whether the company assessment picks them up.",
    narrativePlaceholder: "Describe the course chronologically (in Japanese).",
    exampleTranslationTitle: "The example narrative, in English (reference)",
    exampleTranslation:
      "DrugX 10 mg once daily was started on 2026-01-10 for essential hypertension. Four days later (2026-01-14) the patient felt dizzy on standing up. The reporter considered this minor and reported it as non-serious.\n\nThat evening, however, she fell in the hallway at home because of the dizziness and sustained a right femoral neck fracture. She was taken to hospital by ambulance, admitted the same day, and underwent open reduction and internal fixation the next day. The admission lasted 18 days; she was discharged on 2026-02-02. DrugX was stopped on admission.",
    run: "Triage this case",
    clear: "Clear",
  },

  rag: {
    title: "Ask a report questions, with sources",
    intro:
      "Index a PV report (PDF / text / email) and ask about its contents. Answers are grounded only in the retrieved passages and come back with their sources (document and page).",
    languageNote:
      "The reports are in Japanese, but you can ask in English — the answer follows the language of your question. Source passages are quoted as they appear, in Japanese.",
    indexTitle: "① Index a document",
    demoNote: "Uploads are off in the public demo. Index one of the bundled sample cases instead.",
    indexSample: (label: string) => `Index ${label}`,
    chooseFile: "Choose file",
    fileHint: "PDF / .txt / .eml / .png",
    indexing: "Indexing…",
    upload: "Upload and index",
    indexFailed: (status: number) => `Indexing failed (HTTP ${status})`,
    uploadFailed: (status: number) => `Upload failed (HTTP ${status})`,
    indexedMsg: (name: string, n: number) => `${name}: added ${n} chunks to the index.`,
    indexedTitle: "Indexed",
    chunks: (n: number) => `${n} chunks`,
    askTitle: "② Ask",
    uploadFirst: "Index a document first — questions are answered from indexed documents only.",
    placeholder: "e.g. What adverse events were reported, and what were their outcomes?",
    shortcut: "⌘/Ctrl + Enter to send",
    searching: "Searching…",
    ask: "Ask",
    queryFailed: (status: number) => `Search failed (HTTP ${status})`,
    answer: "Answer",
    sources: (n: number) => `${n} source${n === 1 ? "" : "s"}`,
    clickToOpen: "(click for the passage)",
  },

  samples: {
    kicker: "Sample cases",
    title: "What each case is designed to test",
    introBefore:
      "Each case the demo can run is a synthetic report written to probe one specific behaviour (no real patient data). The expected verdicts are fixed as ground truth in",
    introAfter: ", and the evaluation harness scores against them.",
    inScope: "In scope",
    outOfScope: "Out of scope",
    suspectDrug: "Suspect drug",
    probesTitle: "What this case tests",
    expectedTitle: "Expected verdicts (gold)",
    fullText: "Read the case (English reference translation)",
    fullTextOriginal: "Original (Japanese) — what the pipeline reads",
    readError: "(could not read the case file)",
    footer:
      "All cases are synthetic, written for this project; no real patient data. The package inserts are likewise fictional, modelled on real products.",
  },

  telemetry: {
    title: "Cost and time",
    unpricedSuffix: " + unpriced",
    head: ["Step", "Model", "Timeline", "Time", "In / out tokens", "Cost"],
    noLlm: "— (no LLM)",
    total: "Total (wait)",
    unpriced: "unpriced",
    sec: (ms: number) => `${(ms / 1000).toFixed(1)} s`,
    barTitle: (start: string, dur: string) => `starts +${start} / ${dur}`,
    measured: (asOf: string) =>
      `Measured on this run, not estimated. Priced at OpenAI standard-tier rates as of ${asOf}.`,
    parallel: (sum: string, wall: string) =>
      `Expectedness, causality and MedDRA run in parallel, so the step times add up to more (${sum}) than the actual wait (${wall}).`,
    cached: (pct: number) =>
      `${pct}% of input tokens hit the prompt cache and were billed at the discounted rate. A first run of a case caches less and costs more.`,
    unpricedNote: "Models not in the price table (e.g. local models) are not included in the total.",
    embeddings: "Excludes retrieval embeddings (package inserts, MedDRA) — under a cent at this scale.",
  },
};
