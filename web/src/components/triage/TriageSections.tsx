import type {
  AdverseEventMention,
  CausalityAssessment,
  EventPrecedent,
  ExpectednessAssessment,
  MeddraCoding,
  SeriousnessAssessment,
  TriageContent,
} from "@/lib/types";
import {
  AXIS_LABELS,
  INFLUENCE_SOURCE_LABELS,
  SOURCE_LABELS,
  counts,
  reportedIsSerious,
  verdictTone,
} from "@/lib/labels";
import { Badge, TD, Table, dash } from "./ui";

// The triage view is scanned under time pressure, not read top to bottom, so it
// is ordered by what a reviewer needs first: the headline counts, then one row
// per event. Evidence (criteria, quotes, label passages) sits inside each row's
// disclosure rather than beside the verdicts — the earlier layout repeated the
// same event list across four tables, which made the page long and gave "what
// was decided" and "why" equal visual weight.

type EventRow = {
  term: string;
  ae?: AdverseEventMention;
  meddra?: MeddraCoding;
  ser?: SeriousnessAssessment;
  cau?: CausalityAssessment;
  exp: { drug: string; a: ExpectednessAssessment }[];
  precedent?: EventPrecedent;
};

/** One row per adverse event, joining every axis by term. */
function buildRows(data: TriageContent): EventRow[] {
  const order: string[] = data.extraction.adverse_events.map((e) => e.term);
  // Reviewer-added events appear in the judgment lists without an extraction entry.
  for (const s of data.seriousness) if (!order.includes(s.term)) order.push(s.term);

  return order.map((term, i) => ({
    term,
    ae: data.extraction.adverse_events.find((e) => e.term === term),
    meddra:
      data.meddra.find((m) => m.term === term) ??
      (data.extraction.adverse_events[i]?.term === term ? data.meddra[i] : undefined),
    ser: data.seriousness.find((s) => s.term === term),
    cau: data.causality.find((c) => c.term === term),
    exp: data.expectedness.flatMap((d) =>
      d.assessments.filter((a) => a.term === term).map((a) => ({ drug: d.drug_name, a })),
    ),
    precedent: data.precedent.find((p) => p.term === term && p.n_cases > 0),
  }));
}

function Stat({
  value,
  label,
  tone,
}: {
  value: number;
  label: string;
  tone: "danger" | "warn" | "good" | "muted";
}) {
  const color = {
    danger: "text-danger",
    warn: "text-warn",
    good: "text-good",
    muted: "text-muted",
  }[tone];
  return (
    <div>
      <div
        className={`text-2xl font-bold tabular-nums ${value > 0 ? color : "text-muted"}`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-xs text-muted">{label}</div>
    </div>
  );
}

// Shared by the column header and every event row so the columns line up.
const ROW_GRID =
  "grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_5.5rem_7rem_5rem] sm:gap-y-0";

export default function TriageSections({ data }: { data: TriageContent }) {
  const rows = buildRows(data);
  const pm = data.product_match;

  const nSerious = rows.filter((r) => r.ser?.is_serious).length;
  const nCheck = rows.filter((r) => r.ser?.verdict === "要確認").length;
  const nUnexpected = rows.filter((r) => r.exp.some((e) => e.a.verdict === "未知")).length;
  const nNotExcludable = rows.filter((r) => r.cau?.verdict === "否定できない").length;

  // Serious + not already in the label is the classic expedited-reporting
  // trigger. Surfaced as an aid for the reviewer, not a regulatory decision.
  const flagged = rows.filter(
    (r) => r.ser?.is_serious && (r.exp.length === 0 || r.exp.some((e) => !e.a.is_expected)),
  );

  return (
    <div className="space-y-4">
      {/* ---- headline ---- */}
      <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-bold text-ink">判定サマリー</h3>
          {pm.is_company_product_present ? (
            <Badge tone="good">
              自社品 {pm.matched_products.map((p) => p.name).join("、")}
            </Badge>
          ) : (
            <Badge tone="warn">自社品なし</Badge>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Stat value={rows.length} label="有害事象" tone="muted" />
          <Stat value={nSerious} label="重篤" tone="danger" />
          <Stat value={nCheck} label="要確認" tone="warn" />
          <Stat value={nUnexpected} label="未知" tone="danger" />
          <Stat value={nNotExcludable} label="因果 否定できない" tone="muted" />
        </div>

        {flagged.length > 0 && (
          <div className="mt-4 rounded-lg border border-danger/40 bg-danger-weak px-4 py-3">
            <p className="text-sm font-bold text-danger">
              重篤かつ既知でない事象が {flagged.length} 件 — 迅速報告の検討対象
            </p>
            <p className="mt-1 text-sm text-text">
              {flagged.map((r) => r.term).join("、")}
            </p>
            <p className="mt-1 text-xs text-muted">
              ドラフト作成の補助であり、報告要否の判断そのものではありません。
            </p>
          </div>
        )}
      </section>

      {/* ---- one row per event ---- */}
      <section className="rounded-xl border border-border bg-surface shadow-sm">
        <div className="flex items-baseline justify-between gap-2 border-b border-border p-5 pb-3">
          <h3 className="text-sm font-bold text-ink">事象一覧</h3>
          <p className="text-xs text-muted">行を開くと根拠が表示されます</p>
        </div>

        <div
          className={`${ROW_GRID} hidden border-b border-border px-5 py-2 text-xs font-medium text-muted sm:grid`}
        >
          <div>事象</div>
          <div>MedDRA PT</div>
          <div>重篤度</div>
          <div>因果</div>
          <div>既知/未知</div>
        </div>

        {rows.map((r, i) => (
          <details
            key={`${r.term}-${i}`}
            className="group border-b border-border last:border-b-0"
          >
            <summary className="cursor-pointer list-none px-5 py-3 marker:content-none hover:bg-surface-2">
              <div className={ROW_GRID}>
                <div className="flex items-center gap-2 text-sm font-medium text-ink">
                  <span className="text-muted transition-transform group-open:rotate-90">
                    ›
                  </span>
                  <span className="min-w-0">{r.term}</span>
                </div>
                <div className="text-sm text-text sm:truncate">
                  {r.meddra?.pt_name_ja ? (
                    <>
                      {r.meddra.pt_name_ja}{" "}
                      <span className="font-mono text-xs text-muted">
                        {r.meddra.pt_code}
                      </span>
                    </>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </div>
                <div>
                  {r.ser ? (
                    <Badge tone={verdictTone("seriousness", r.ser.verdict)}>
                      {r.ser.verdict}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted">—</span>
                  )}
                </div>
                <div>
                  {r.cau ? (
                    <Badge tone={verdictTone("causality", r.cau.verdict)}>
                      {r.cau.verdict}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted">—</span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  {r.exp.length === 0 ? (
                    <span className="text-xs text-muted">—</span>
                  ) : (
                    r.exp.map((e) => (
                      <Badge key={e.drug} tone={verdictTone("expectedness", e.a.verdict)}>
                        {e.a.verdict}
                      </Badge>
                    ))
                  )}
                </div>
              </div>
            </summary>

            {/* ---- evidence, on demand ---- */}
            <div className="space-y-3 border-t border-border bg-surface-2 px-5 py-4 text-sm">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
                <span>
                  出典:{" "}
                  <span className="text-text">
                    {r.ae ? (SOURCE_LABELS[r.ae.source] ?? r.ae.source) : "レビュアー追加"}
                  </span>
                </span>
                <span>
                  発現日: <span className="text-text">{dash(r.ae?.onset_date)}</span>
                </span>
                <span>
                  転帰: <span className="text-text">{dash(r.ae?.outcome)}</span>
                </span>
                <span>
                  報告重篤度:{" "}
                  <span className="text-text">{dash(r.ae?.seriousness_reported)}</span>
                </span>
                {r.meddra?.coded_by && (
                  <span>
                    コード由来: <span className="text-text">{r.meddra.coded_by}</span>
                  </span>
                )}
              </div>

              {r.ser && (
                <div>
                  <p className="text-xs font-bold text-ink">
                    重篤度（企業評価 / ICH E2A）
                    {(() => {
                      const rep = reportedIsSerious(r.ser.reported);
                      return rep !== null && rep !== r.ser.is_serious ? (
                        <span className="ml-2 font-normal text-warn">
                          ⚠️ 報告（{r.ser.reported}）と差異
                        </span>
                      ) : null;
                    })()}
                  </p>
                  {r.ser.hits.length > 0 && (
                    <p className="mt-0.5 text-xs text-text">
                      該当基準: {r.ser.hits.map((h) => h.criterion).join("、")}
                    </p>
                  )}
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">
                    {dash(
                      r.ser.hits.find((h) => h.evidence_quote)?.evidence_quote ??
                        r.ser.rationale,
                    )}
                  </p>
                </div>
              )}

              {r.cau && (
                <div>
                  <p className="text-xs font-bold text-ink">
                    因果関係（時間的・保守的）
                    {r.cau.onset_relation && (
                      <span className="ml-2 font-normal text-muted">
                        {r.cau.onset_relation}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">
                    {dash(r.cau.evidence_quote ?? r.cau.rationale)}
                  </p>
                </div>
              )}

              {r.exp.map((e) => (
                <div key={e.drug}>
                  <p className="text-xs font-bold text-ink">
                    既知/未知 — {e.drug}
                    {e.a.match_type && (
                      <span className="ml-2 font-normal text-muted">
                        一致: {e.a.match_type}
                      </span>
                    )}
                    {e.a.evidence_section && (
                      <span className="ml-2 font-normal text-muted">
                        {e.a.evidence_section}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">
                    {dash(e.a.evidence_quote ?? e.a.rationale)}
                  </p>
                </div>
              ))}

              {r.precedent && (
                <div>
                  <p className="text-xs font-bold text-ink">
                    過去症例（同一PT {r.precedent.n_cases} 件）
                    {r.precedent.conflicts.length > 0 && (
                      <span className="ml-2 font-normal text-warn">
                        ⚠️ 不一致:{" "}
                        {r.precedent.conflicts.map((a) => AXIS_LABELS[a] ?? a).join("・")}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    重篤度 {counts(r.precedent.seriousness)} ／ 因果{" "}
                    {counts(r.precedent.causality)}
                    {r.precedent.case_ids.length > 0 && (
                      <> ／ 参照: {r.precedent.case_ids.join("、")}</>
                    )}
                  </p>
                </div>
              )}
            </div>
          </details>
        ))}
      </section>

      {/* ---- supporting detail, collapsed by default ---- */}
      <details className="rounded-xl border border-border bg-surface shadow-sm">
        <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
          患者・自社品の詳細
        </summary>
        <div className="space-y-4 border-t border-border p-5">
          <div className="flex gap-8">
            <div>
              <div className="text-xs text-muted">年齢</div>
              <div className="mt-0.5 text-lg font-bold text-ink">
                {dash(data.extraction.patient.age)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">性別</div>
              <div className="mt-0.5 text-lg font-bold text-ink">
                {dash(data.extraction.patient.sex)}
              </div>
            </div>
          </div>
          {pm.matched_products.length > 0 ? (
            <ul className="space-y-1">
              {pm.matched_products.map((p) => (
                <li key={p.name} className="text-sm text-text">
                  <span className="font-medium text-ink">{p.name}</span>
                  <span className="text-muted">
                    {" "}
                    （ヒット語:{" "}
                    <code className="rounded bg-surface-2 px-1 font-mono text-xs">
                      {p.matched_via}
                    </code>
                    ）
                  </span>
                  {p.notes && <span className="block text-xs text-muted">{p.notes}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">自社品の該当なし。</p>
          )}
        </div>
      </details>

      <details className="rounded-xl border border-border bg-surface shadow-sm">
        <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
          過去データの扱い
          <span className="ml-2 font-mono text-xs font-normal text-muted">
            {data.influence_mode === "applied" ? "反映" : "参考"}
          </span>
        </summary>
        <div className="border-t border-border p-5">
          {data.influence.length === 0 ? (
            <p className="text-sm text-muted">
              今回、過去データ（IME・過去症例）による調整や参考情報はありませんでした。
            </p>
          ) : (
            <Table
              head={[
                "事象",
                "軸",
                "由来",
                data.influence_mode === "applied" ? "変更" : "メモ",
              ]}
            >
              {data.influence.map((it, i) => (
                <tr key={`${it.term}-${i}`}>
                  <td className={`${TD} font-medium text-ink`}>{it.term}</td>
                  <td className={`${TD} text-xs`}>{AXIS_LABELS[it.axis] ?? it.axis}</td>
                  <td className={`${TD} text-xs`}>
                    {INFLUENCE_SOURCE_LABELS[it.source] ?? it.source}
                  </td>
                  <td className={`${TD} text-xs text-muted`}>
                    {it.applied ? `${it.from_verdict}→${it.to_verdict}` : it.note}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </details>

      <details className="rounded-xl border border-border bg-surface shadow-sm">
        <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
          読み取ったテキスト（出典）
        </summary>
        <pre className="max-h-96 overflow-auto border-t border-border p-5 text-xs leading-relaxed whitespace-pre-wrap text-text">
          {data.source_text}
        </pre>
      </details>
    </div>
  );
}
