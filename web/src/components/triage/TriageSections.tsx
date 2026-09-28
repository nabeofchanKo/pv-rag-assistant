import type {
  AdverseEventMention,
  CausalityAssessment,
  EventPrecedent,
  ExpectednessAssessment,
  MeddraCoding,
  SeriousnessAssessment,
  ReviewOutcome,
  TriageContent,
} from "@/lib/types";
import { counts, reportedIsSerious, verdictTone } from "@/lib/labels";
import { useDict, useTerm } from "@/i18n/LocaleProvider";
import TelemetryPanel from "./TelemetryPanel";
import { Badge, TD, Table, dash } from "./ui";
import { type VerdictChange, buildChanges, changeKey, indexChanges } from "./changes";

// The triage view is scanned under time pressure, not read top to bottom, so it
// is ordered by what a reviewer needs first: the headline counts, then one row
// per event. Evidence (criteria, quotes, label passages) sits inside each row's
// disclosure rather than beside the verdicts — the earlier layout repeated the
// same event list across four tables, which made the page long and gave "what
// was decided" and "why" equal visual weight.
//
// Language: every fixed value (verdict, criterion, coding route, ...) is shown
// through useTerm(); free text from the case or the model (terms, quotes,
// rationales, notes) is shown as it came.

type Axis = "seriousness" | "causality" | "expectedness";

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

/**
 * A verdict, plus where it came from when it is not what the model first said.
 * Showing "non-serious ->" under the badge keeps both values visible at once,
 * which reads better than a toggle that hides one of them.
 */
function VerdictCell({
  axis,
  verdict,
  change,
}: {
  axis: Axis;
  verdict?: string;
  change?: VerdictChange;
}) {
  const t = useDict().sections;
  const term = useTerm();
  if (!verdict) return <span className="text-xs text-muted">—</span>;
  return (
    <div>
      <Badge tone={verdictTone(axis, verdict)}>{term(verdict)}</Badge>
      {change && (
        <div className="mt-0.5 text-[10px] leading-tight text-muted">
          <span className="line-through">{term(change.from)}</span> {t.changedVia}{" "}
          <span className={change.source === "reviewer" ? "text-accent" : "text-warn"}>
            {change.source === "reviewer" ? t.byReviewer : t.byPastData}
          </span>
        </div>
      )}
    </div>
  );
}

// Shared by the column header and every event row so the columns line up.
const ROW_GRID =
  "grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_6.5rem_8rem_6.5rem] sm:gap-y-0";

export default function TriageSections({
  data,
  review,
}: {
  data: TriageContent;
  review?: ReviewOutcome | null;
}) {
  const d = useDict();
  const t = d.sections;
  const v = d.vocab;
  const term = useTerm();
  const axisLabel = (a: string) => v.axis[a as Axis] ?? a;
  const count = (x: Record<string, number> | undefined) =>
    counts(x, (k, n) => v.countItem(term(k), n), v.countSep);

  const rows = buildRows(data);
  const pm = data.product_match;
  const changes = buildChanges(data, review);
  const changeIndex = indexChanges(changes);

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
          <h3 className="text-sm font-bold text-ink">{t.summary}</h3>
          {pm.is_company_product_present ? (
            <Badge tone="good">
              {t.companyProduct(pm.matched_products.map((p) => p.name).join(v.listSep))}
            </Badge>
          ) : (
            <Badge tone="warn">{t.noCompanyProduct}</Badge>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Stat value={rows.length} label={t.stats.events} tone="muted" />
          <Stat value={nSerious} label={t.stats.serious} tone="danger" />
          <Stat value={nCheck} label={t.stats.check} tone="warn" />
          <Stat value={nUnexpected} label={t.stats.unexpected} tone="danger" />
          <Stat value={nNotExcludable} label={t.stats.notExcludable} tone="muted" />
        </div>

        {flagged.length > 0 && (
          <div className="mt-4 rounded-lg border border-danger/40 bg-danger-weak px-4 py-3">
            <p className="text-sm font-bold text-danger">{t.flagged(flagged.length)}</p>
            <p className="mt-1 text-sm text-text">
              {flagged.map((r) => r.term).join(v.listSep)}
            </p>
            <p className="mt-1 text-xs text-muted">{t.flaggedNote}</p>
          </div>
        )}
      </section>

      {/* ---- what human review and past data actually changed ---- */}
      {changes.length > 0 && (
        <section className="rounded-xl border border-accent/40 bg-surface shadow-sm">
          <div className="border-b border-border p-5 pb-3">
            <h3 className="text-sm font-bold text-ink">{t.changesTitle(changes.length)}</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted">{t.changesNote}</p>
          </div>
          <div className="p-5 pt-3">
            <Table head={t.changesHead}>
              {changes.map((c, i) => (
                <tr key={`${c.axis}-${c.term}-${i}`}>
                  <td className={`${TD} font-medium text-ink`}>
                    {c.term}
                    {c.drug && (
                      <span className="ml-1 text-xs text-muted">{v.paren(c.drug)}</span>
                    )}
                  </td>
                  <td className={`${TD} text-xs`}>{axisLabel(c.axis)}</td>
                  <td className={TD}>
                    <span className="text-xs text-muted line-through">{term(c.from)}</span>
                  </td>
                  <td className={TD}>
                    <Badge tone={verdictTone(c.axis as Axis, c.to)}>{term(c.to)}</Badge>
                  </td>
                  <td className={`${TD} text-xs`}>
                    <span
                      className={
                        c.source === "reviewer" ? "text-accent" : "text-warn"
                      }
                    >
                      {v.changeSource[c.source]}
                    </span>
                  </td>
                  <td className={`${TD} text-xs text-muted`}>{dash(c.reason)}</td>
                </tr>
              ))}
            </Table>
          </div>
        </section>
      )}

      {/* ---- one row per event ---- */}
      <section className="rounded-xl border border-border bg-surface shadow-sm">
        <div className="flex items-baseline justify-between gap-2 border-b border-border p-5 pb-3">
          <h3 className="text-sm font-bold text-ink">{t.eventsTitle}</h3>
          <p className="text-xs text-muted">{t.eventsHint}</p>
        </div>

        <div
          className={`${ROW_GRID} hidden border-b border-border px-5 py-2 text-xs font-medium text-muted sm:grid`}
        >
          <div>{t.cols.event}</div>
          <div>{t.cols.pt}</div>
          <div>{t.cols.seriousness}</div>
          <div>{t.cols.causality}</div>
          <div>{t.cols.expectedness}</div>
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
                <VerdictCell
                  axis="seriousness"
                  verdict={r.ser?.verdict}
                  change={changeIndex.get(changeKey("seriousness", r.term))}
                />
                <VerdictCell
                  axis="causality"
                  verdict={r.cau?.verdict}
                  change={changeIndex.get(changeKey("causality", r.term))}
                />
                <div className="flex flex-wrap gap-1">
                  {r.exp.length === 0 ? (
                    <span className="text-xs text-muted">—</span>
                  ) : (
                    r.exp.map((e) => (
                      <VerdictCell
                        key={e.drug}
                        axis="expectedness"
                        verdict={e.a.verdict}
                        change={changeIndex.get(
                          changeKey("expectedness", r.term, e.drug),
                        )}
                      />
                    ))
                  )}
                </div>
              </div>
            </summary>

            {/* ---- evidence, on demand ---- */}
            <div className="space-y-3 border-t border-border bg-surface-2 px-5 py-4 text-sm">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
                <span>
                  {t.source}:{" "}
                  <span className="text-text">
                    {r.ae ? (v.aeSource[r.ae.source] ?? r.ae.source) : t.reviewerAdded}
                  </span>
                </span>
                <span>
                  {t.onset}: <span className="text-text">{dash(r.ae?.onset_date)}</span>
                </span>
                <span>
                  {t.outcome}: <span className="text-text">{dash(term(r.ae?.outcome))}</span>
                </span>
                <span>
                  {t.reportedSeriousness}:{" "}
                  <span className="text-text">{dash(term(r.ae?.seriousness_reported))}</span>
                </span>
                {r.meddra?.coded_by && (
                  <span>
                    {t.codedBy}: <span className="text-text">{term(r.meddra.coded_by)}</span>
                  </span>
                )}
              </div>

              {r.ser && (
                <div>
                  <p className="text-xs font-bold text-ink">
                    {t.serTitle}
                    {(() => {
                      const rep = reportedIsSerious(r.ser.reported);
                      return rep !== null && rep !== r.ser.is_serious ? (
                        <span className="ml-2 font-normal text-warn">
                          {t.reportedDiffers(term(r.ser.reported))}
                        </span>
                      ) : null;
                    })()}
                  </p>
                  {r.ser.hits.length > 0 && (
                    <p className="mt-0.5 text-xs text-text">
                      {t.criteria}: {r.ser.hits.map((h) => term(h.criterion)).join(v.listSep)}
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
                    {t.cauTitle}
                    {r.cau.onset_relation && (
                      <span className="ml-2 font-normal text-muted">
                        {term(r.cau.onset_relation)}
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
                    {t.expTitle(e.drug)}
                    {e.a.match_type && (
                      <span className="ml-2 font-normal text-muted">
                        {t.match}: {term(e.a.match_type)}
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
                    {t.precedentTitle(r.precedent.n_cases)}
                    {r.precedent.conflicts.length > 0 && (
                      <span className="ml-2 font-normal text-warn">
                        {t.conflicts}: {r.precedent.conflicts.map(axisLabel).join(v.listSep)}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {v.axis.seriousness} {count(r.precedent.seriousness)}
                    {v.countSep}
                    {v.axis.causality} {count(r.precedent.causality)}
                    {r.precedent.case_ids.length > 0 && (
                      <>
                        {v.countSep}
                        {t.refs}: {r.precedent.case_ids.join(v.listSep)}
                      </>
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
          {t.patientTitle}
        </summary>
        <div className="space-y-4 border-t border-border p-5">
          <div className="flex gap-8">
            <div>
              <div className="text-xs text-muted">{t.age}</div>
              <div className="mt-0.5 text-lg font-bold text-ink">
                {dash(data.extraction.patient.age)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">{t.sex}</div>
              <div className="mt-0.5 text-lg font-bold text-ink">
                {dash(term(data.extraction.patient.sex))}
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
                    ({t.hitTerm}:{" "}
                    <code className="rounded bg-surface-2 px-1 font-mono text-xs">
                      {p.matched_via}
                    </code>
                    )
                  </span>
                  {p.notes && <span className="block text-xs text-muted">{p.notes}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t.noProduct}</p>
          )}
        </div>
      </details>

      <details className="rounded-xl border border-border bg-surface shadow-sm">
        <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
          {t.influenceTitle}
          <span className="ml-2 font-mono text-xs font-normal text-muted">
            {data.influence_mode === "applied"
              ? t.influenceMode.applied
              : t.influenceMode.advisory}
          </span>
        </summary>
        <div className="border-t border-border p-5">
          {data.influence.length === 0 ? (
            <p className="text-sm text-muted">{t.influenceNone}</p>
          ) : (
            <Table
              head={[
                ...t.influenceHead,
                data.influence_mode === "applied" ? t.influenceChange : t.influenceMemo,
              ]}
            >
              {data.influence.map((it, i) => (
                <tr key={`${it.term}-${i}`}>
                  <td className={`${TD} font-medium text-ink`}>{it.term}</td>
                  <td className={`${TD} text-xs`}>{axisLabel(it.axis)}</td>
                  <td className={`${TD} text-xs`}>
                    {v.influenceSource[it.source as keyof typeof v.influenceSource] ??
                      it.source}
                  </td>
                  <td className={`${TD} text-xs text-muted`}>
                    {it.applied ? `${term(it.from_verdict)}→${term(it.to_verdict)}` : it.note}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </details>

      <TelemetryPanel telemetry={data.telemetry} />

      <details className="rounded-xl border border-border bg-surface shadow-sm">
        <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
          {d.triage.sourceText}
        </summary>
        <pre className="max-h-96 overflow-auto border-t border-border p-5 text-xs leading-relaxed whitespace-pre-wrap text-text">
          {data.source_text}
        </pre>
      </details>
    </div>
  );
}
