"use client";

import { useMemo, useState } from "react";
import Spinner from "@/components/Spinner";
import {
  AXIS_LABELS,
  CAU_OPTIONS,
  EXP_OPTIONS,
  EXTRACTION_EDIT_KIND_LABELS,
  SER_OPTIONS,
  verdictTone,
} from "@/lib/labels";
import type {
  AddedEvent,
  RecodedEvent,
  ReviewDecision,
  TriageDraft,
  TriageResult,
  VerdictOverride,
} from "@/lib/types";
import {
  BTN_PRIMARY,
  BTN_SECONDARY,
  Badge,
  INPUT_CLASS,
  Section,
  TD,
  Table,
  dash,
} from "./ui";

const ovKey = (axis: string, term: string, drug?: string | null) =>
  `${axis}::${term}::${drug ?? ""}`;

/** FastAPI `detail` is a string for our HTTPExceptions, an array for body-validation errors. */
function errText(data: unknown, status: number): string {
  const d = (data as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d
      .map((x) =>
        typeof x === "string" ? x : ((x as { msg?: string })?.msg ?? JSON.stringify(x)),
      )
      .join(" / ");
  return `確定に失敗しました (HTTP ${status})`;
}

type AddedDraft = {
  term: string;
  pt_code: string;
  pt_name: string;
  seriousness: string;
  causality: string;
};

const NEW_ROW: AddedDraft = {
  term: "",
  pt_code: "",
  pt_name: "",
  seriousness: "要確認",
  causality: "否定できない",
};

// ---------------- awaiting_review: the review form ----------------

function ReviewForm({
  draft,
  onFinalized,
}: {
  draft: TriageDraft;
  onFinalized: (r: TriageResult) => void;
}) {
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [ovVerdict, setOvVerdict] = useState<Record<string, string>>({});
  const [ovRationale, setOvRationale] = useState<Record<string, string>>({});
  const [imeChecked, setImeChecked] = useState<Record<string, boolean>>({});
  const [imeRationale, setImeRationale] = useState<Record<string, string>>({});
  const [removed, setRemoved] = useState<Record<string, boolean>>({});
  const [recode, setRecode] = useState<Record<string, { code: string; name: string }>>({});
  const [added, setAdded] = useState<AddedDraft[]>([]);
  const [submitting, setSubmitting] = useState<null | "approve" | "reject">(null);
  const [error, setError] = useState<string | null>(null);

  const medByTerm = useMemo(
    () => Object.fromEntries(draft.meddra.map((m) => [m.term, m])),
    [draft.meddra],
  );

  // Unique coded PTs — the only events that can be promoted to the IME list.
  const imeRows = useMemo(() => {
    const seen = new Set<string>();
    const rows: { term: string; pt_name: string; pt_code: string }[] = [];
    for (const m of draft.meddra) {
      if (!m.pt_code || seen.has(m.pt_code)) continue;
      seen.add(m.pt_code);
      rows.push({ term: m.term, pt_name: m.pt_name_ja ?? "—", pt_code: m.pt_code });
    }
    return rows;
  }, [draft.meddra]);

  function verdictOf(axis: string, term: string, original: string, drug?: string | null) {
    return ovVerdict[ovKey(axis, term, drug)] ?? original;
  }

  function setVerdict(axis: string, term: string, v: string, drug?: string | null) {
    setOvVerdict((p) => ({ ...p, [ovKey(axis, term, drug)]: v }));
  }

  function collect(): Omit<ReviewDecision, "action" | "reviewer" | "note"> {
    const overrides: VerdictOverride[] = [];

    for (const s of draft.seriousness) {
      const k = ovKey("seriousness", s.term);
      const v = ovVerdict[k];
      if (v && v !== s.verdict)
        overrides.push({
          axis: "seriousness",
          term: s.term,
          new_verdict: v,
          rationale: ovRationale[k]?.trim() || null,
        });
    }
    for (const c of draft.causality) {
      const k = ovKey("causality", c.term);
      const v = ovVerdict[k];
      if (v && v !== c.verdict)
        overrides.push({
          axis: "causality",
          term: c.term,
          new_verdict: v,
          rationale: ovRationale[k]?.trim() || null,
        });
    }
    for (const d of draft.expectedness) {
      for (const a of d.assessments) {
        const k = ovKey("expectedness", a.term, d.drug_name);
        const v = ovVerdict[k];
        if (v && v !== a.verdict)
          overrides.push({
            axis: "expectedness",
            term: a.term,
            drug_name: d.drug_name,
            new_verdict: v,
            rationale: ovRationale[k]?.trim() || null,
          });
      }
    }

    const ime_promotions = imeRows
      .filter((r) => imeChecked[r.pt_code])
      .map((r) => ({
        pt_code: r.pt_code,
        pt_name: r.pt_name,
        rationale: imeRationale[r.pt_code]?.trim() || null,
      }));

    const removed_terms = draft.extraction.adverse_events
      .filter((ae) => removed[ae.term])
      .map((ae) => ae.term);

    const recoded: RecodedEvent[] = [];
    for (const ae of draft.extraction.adverse_events) {
      if (removed[ae.term]) continue;
      const orig = medByTerm[ae.term]?.pt_code ?? "";
      const cur = recode[ae.term];
      const code = cur?.code.trim() ?? "";
      if (code && code !== orig)
        recoded.push({
          term: ae.term,
          pt_code: code,
          pt_name: (cur?.name.trim() || code),
        });
    }

    const added_events: AddedEvent[] = added
      .filter((a) => a.term.trim())
      .map((a) => ({
        term: a.term.trim(),
        pt_code: a.pt_code.trim() || null,
        pt_name: a.pt_name.trim() || null,
        seriousness: a.seriousness,
        causality: a.causality,
      }));

    return { overrides, ime_promotions, removed_terms, added_events, recoded };
  }

  async function submit(action: "approve" | "reject") {
    if (!reviewer.trim()) {
      setError("レビュー担当者名は必須です。");
      return;
    }
    setSubmitting(action);
    setError(null);
    const edits = collect();
    const body: ReviewDecision =
      action === "approve"
        ? { action, reviewer: reviewer.trim(), note: note.trim() || null, ...edits }
        : {
            action,
            reviewer: reviewer.trim(),
            note: note.trim() || null,
            overrides: [],
            ime_promotions: [],
            removed_terms: [],
            added_events: [],
            recoded: [],
          };
    try {
      const res = await fetch(`/api/cases/${draft.thread_id}/approve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(errText(data, res.status));
      onFinalized(data as TriageResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(null);
    }
  }

  const overrideTable = (
    axis: "seriousness" | "causality",
    items: { term: string; verdict: string }[],
    options: string[],
  ) =>
    items.length === 0 ? null : (
      <div className="mt-3">
        <p className="mb-1 text-xs font-medium text-muted">{AXIS_LABELS[axis]}</p>
        <Table head={["事象", "現在", "変更後", "変更理由"]}>
          {items.map((x) => {
            const k = ovKey(axis, x.term);
            const cur = verdictOf(axis, x.term, x.verdict);
            const changed = cur !== x.verdict;
            return (
              <tr key={k}>
                <td className={`${TD} font-medium text-ink`}>{x.term}</td>
                <td className={TD}>
                  <Badge tone={verdictTone(axis, x.verdict)}>{x.verdict}</Badge>
                </td>
                <td className={TD}>
                  <select
                    aria-label={`${AXIS_LABELS[axis]} ${x.term} の変更後`}
                    className={`${INPUT_CLASS} ${changed ? "border-accent" : ""}`}
                    value={cur}
                    onChange={(e) => setVerdict(axis, x.term, e.target.value)}
                  >
                    {options.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                </td>
                <td className={TD}>
                  <input
                    aria-label={`${AXIS_LABELS[axis]} ${x.term} の変更理由`}
                    className={INPUT_CLASS}
                    placeholder={changed ? "変更理由（任意）" : "—"}
                    value={ovRationale[k] ?? ""}
                    onChange={(e) =>
                      setOvRationale((p) => ({ ...p, [k]: e.target.value }))
                    }
                  />
                </td>
              </tr>
            );
          })}
        </Table>
      </div>
    );

  return (
    <Section num="⑧" title="レビュー・承認（HITL）">
      {draft.escalations.length > 0 ? (
        <p className="rounded-lg border border-warn/40 bg-warn-weak px-3 py-2 text-sm text-warn">
          安全側で『要確認 / 評価不能』の項目が {draft.escalations.length} 件あります。判断のうえ承認してください。
        </p>
      ) : (
        <p className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-muted">
          安全側の要確認項目はありません。内容を確認して承認してください。
        </p>
      )}

      {/* reviewer + note */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs font-medium text-muted">
            レビュー担当者名 <span className="text-danger">*必須</span>
          </span>
          <input
            className={`${INPUT_CLASS} mt-1`}
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            placeholder="例：田中PV担当"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-muted">全体所見（任意）</span>
          <input
            className={`${INPUT_CLASS} mt-1`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="所見があれば記入"
          />
        </label>
      </div>

      {/* verdict overrides */}
      <div className="mt-6 border-t border-border pt-4">
        <p className="text-sm font-bold text-ink">判定の上書き（任意）</p>
        <p className="mt-1 text-xs text-muted">
          「変更後」を変えた項目だけが上書きされます。元の判定は監査証跡として保持されます。
        </p>
        {overrideTable("seriousness", draft.seriousness, SER_OPTIONS)}
        {overrideTable("causality", draft.causality, CAU_OPTIONS)}
        {draft.expectedness.map((d) => (
          <div key={d.drug_name} className="mt-3">
            <p className="mb-1 text-xs font-medium text-muted">
              {AXIS_LABELS.expectedness}（{d.drug_name}）
            </p>
            <Table head={["事象", "現在", "変更後", "変更理由"]}>
              {d.assessments.map((a) => {
                const k = ovKey("expectedness", a.term, d.drug_name);
                const cur = verdictOf("expectedness", a.term, a.verdict, d.drug_name);
                const changed = cur !== a.verdict;
                return (
                  <tr key={k}>
                    <td className={`${TD} font-medium text-ink`}>{a.term}</td>
                    <td className={TD}>
                      <Badge tone={verdictTone("expectedness", a.verdict)}>
                        {a.verdict}
                      </Badge>
                    </td>
                    <td className={TD}>
                      <select
                        aria-label={`既知/未知 ${a.term} の変更後`}
                        className={`${INPUT_CLASS} ${changed ? "border-accent" : ""}`}
                        value={cur}
                        onChange={(e) =>
                          setVerdict("expectedness", a.term, e.target.value, d.drug_name)
                        }
                      >
                        {EXP_OPTIONS.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={TD}>
                      <input
                        aria-label={`既知/未知 ${a.term} の変更理由`}
                        className={INPUT_CLASS}
                        placeholder={changed ? "変更理由（任意）" : "—"}
                        value={ovRationale[k] ?? ""}
                        onChange={(e) =>
                          setOvRationale((p) => ({ ...p, [k]: e.target.value }))
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </Table>
          </div>
        ))}
      </div>

      {/* IME promotion */}
      {imeRows.length > 0 && (
        <div className="mt-6 border-t border-border pt-4">
          <p className="text-sm font-bold text-ink">IMEリストへの昇格（任意）</p>
          <p className="mt-1 text-xs text-muted">
            「医学的に重要」と判断したPTを追加すると、今後の症例で同じPTの事象が自動的に重篤（criterion 6）になります。
          </p>
          <div className="mt-3">
            <Table head={["IMEに追加", "事象", "PT名", "PTコード", "昇格理由"]}>
              {imeRows.map((r) => (
                <tr key={r.pt_code}>
                  <td className={TD}>
                    <input
                      type="checkbox"
                      aria-label={`${r.pt_name} をIMEに追加`}
                      className="h-4 w-4 accent-[var(--accent)]"
                      checked={!!imeChecked[r.pt_code]}
                      onChange={(e) =>
                        setImeChecked((p) => ({ ...p, [r.pt_code]: e.target.checked }))
                      }
                    />
                  </td>
                  <td className={`${TD} font-medium text-ink`}>{r.term}</td>
                  <td className={TD}>{r.pt_name}</td>
                  <td className={`${TD} font-mono text-xs`}>{r.pt_code}</td>
                  <td className={TD}>
                    <input
                      aria-label={`${r.pt_name} の昇格理由`}
                      className={INPUT_CLASS}
                      placeholder="昇格理由（任意）"
                      value={imeRationale[r.pt_code] ?? ""}
                      onChange={(e) =>
                        setImeRationale((p) => ({ ...p, [r.pt_code]: e.target.value }))
                      }
                    />
                  </td>
                </tr>
              ))}
            </Table>
          </div>
        </div>
      )}

      {/* extraction edits */}
      <div className="mt-6 border-t border-border pt-4">
        <p className="text-sm font-bold text-ink">抽出の修正（任意）</p>
        <p className="mt-1 text-xs text-muted">
          誤抽出は「削除」にチェック。MedDRAが違う場合は PTコード / PT名 を直接修正。
        </p>
        <div className="mt-3">
          <Table head={["削除", "事象", "PTコード", "PT名"]}>
            {draft.extraction.adverse_events.map((ae, i) => {
              const m = medByTerm[ae.term];
              const cur = recode[ae.term] ?? {
                code: m?.pt_code ?? "",
                name: m?.pt_name_ja ?? "",
              };
              const isRemoved = !!removed[ae.term];
              return (
                <tr key={`${ae.term}-${i}`} className={isRemoved ? "opacity-50" : ""}>
                  <td className={TD}>
                    <input
                      type="checkbox"
                      aria-label={`${ae.term} を削除`}
                      className="h-4 w-4 accent-[var(--danger)]"
                      checked={isRemoved}
                      onChange={(e) =>
                        setRemoved((p) => ({ ...p, [ae.term]: e.target.checked }))
                      }
                    />
                  </td>
                  <td className={`${TD} font-medium text-ink`}>{ae.term}</td>
                  <td className={TD}>
                    <input
                      aria-label={`${ae.term} のPTコード`}
                      className={`${INPUT_CLASS} font-mono`}
                      disabled={isRemoved}
                      value={cur.code}
                      onChange={(e) =>
                        setRecode((p) => ({
                          ...p,
                          [ae.term]: { code: e.target.value, name: cur.name },
                        }))
                      }
                    />
                  </td>
                  <td className={TD}>
                    <input
                      aria-label={`${ae.term} のPT名`}
                      className={INPUT_CLASS}
                      disabled={isRemoved}
                      value={cur.name}
                      onChange={(e) =>
                        setRecode((p) => ({
                          ...p,
                          [ae.term]: { code: cur.code, name: e.target.value },
                        }))
                      }
                    />
                  </td>
                </tr>
              );
            })}
          </Table>
        </div>

        <p className="mt-4 text-xs text-muted">
          見落とし事象を追加（判定は手入力。安全側の既定値が入っています）。
        </p>
        {added.length > 0 && (
          <div className="mt-2">
            <Table head={["事象", "PTコード", "PT名", "重篤度", "因果", ""]}>
              {added.map((row, i) => {
                const upd = (patch: Partial<AddedDraft>) =>
                  setAdded((p) => p.map((r, j) => (j === i ? { ...r, ...patch } : r)));
                return (
                  <tr key={i}>
                    <td className={TD}>
                      <input
                        aria-label={`追加事象 ${i + 1} の名称`}
                        className={INPUT_CLASS}
                        placeholder="事象名"
                        value={row.term}
                        onChange={(e) => upd({ term: e.target.value })}
                      />
                    </td>
                    <td className={TD}>
                      <input
                        aria-label={`追加事象 ${i + 1} のPTコード`}
                        className={`${INPUT_CLASS} font-mono`}
                        value={row.pt_code}
                        onChange={(e) => upd({ pt_code: e.target.value })}
                      />
                    </td>
                    <td className={TD}>
                      <input
                        aria-label={`追加事象 ${i + 1} のPT名`}
                        className={INPUT_CLASS}
                        value={row.pt_name}
                        onChange={(e) => upd({ pt_name: e.target.value })}
                      />
                    </td>
                    <td className={TD}>
                      <select
                        aria-label={`追加事象 ${i + 1} の重篤度`}
                        className={INPUT_CLASS}
                        value={row.seriousness}
                        onChange={(e) => upd({ seriousness: e.target.value })}
                      >
                        {SER_OPTIONS.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={TD}>
                      <select
                        aria-label={`追加事象 ${i + 1} の因果`}
                        className={INPUT_CLASS}
                        value={row.causality}
                        onChange={(e) => upd({ causality: e.target.value })}
                      >
                        {CAU_OPTIONS.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={TD}>
                      <button
                        type="button"
                        aria-label={`追加事象 ${i + 1} を削除`}
                        className="rounded px-2 py-1 text-sm text-muted hover:text-danger"
                        onClick={() => setAdded((p) => p.filter((_, j) => j !== i))}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                );
              })}
            </Table>
          </div>
        )}
        <button
          type="button"
          className={`${BTN_SECONDARY} mt-2 px-3 py-1.5 text-xs`}
          onClick={() => setAdded((p) => [...p, { ...NEW_ROW }])}
        >
          ＋ 事象を追加
        </button>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-danger/40 bg-danger-weak px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 flex flex-wrap gap-3 border-t border-border pt-4">
        <button
          type="button"
          className={BTN_PRIMARY}
          disabled={submitting !== null}
          onClick={() => submit("approve")}
        >
          {submitting === "approve" && <Spinner />}
          承認する
        </button>
        <button
          type="button"
          className={BTN_SECONDARY}
          disabled={submitting !== null}
          onClick={() => submit("reject")}
        >
          {submitting === "reject" && <Spinner />}
          却下する
        </button>
      </div>
    </Section>
  );
}

// ---------------- approved / rejected: the audit trail ----------------

function ReviewAudit({
  result,
  onReset,
}: {
  result: TriageResult;
  onReset: () => void;
}) {
  const r = result.review;
  const approved = result.status === "approved";
  let when = r.reviewed_at;
  try {
    when = new Date(r.reviewed_at).toLocaleString("ja-JP");
  } catch {
    /* keep the raw value */
  }

  return (
    <Section num="⑧" title="レビュー・承認（HITL）">
      <p
        className={`rounded-lg border px-3 py-2 text-sm ${
          approved
            ? "border-good/40 bg-good-weak text-good"
            : "border-danger/40 bg-danger-weak text-danger"
        }`}
      >
        {approved ? "✅ 承認済み" : "⛔ 却下"} — 担当: {r.reviewer} / {when}
      </p>
      {r.note && <p className="mt-2 text-xs text-muted">所見: {r.note}</p>}

      <div className="mt-4">
        <p className="text-sm font-bold text-ink">人手による上書き（監査証跡）</p>
        {r.overrides.length === 0 ? (
          <p className="mt-1 text-xs text-muted">上書きなし（ドラフトのまま確定）。</p>
        ) : (
          <div className="mt-2">
            <Table head={["軸", "事象", "製品", "元の判定", "変更後", "理由"]}>
              {r.overrides.map((o, i) => (
                <tr key={`${o.axis}-${o.term}-${i}`}>
                  <td className={`${TD} text-xs`}>{AXIS_LABELS[o.axis] ?? o.axis}</td>
                  <td className={`${TD} font-medium text-ink`}>{o.term}</td>
                  <td className={`${TD} text-xs`}>{dash(o.drug_name)}</td>
                  <td className={TD}>
                    <Badge tone="muted">{o.original_verdict}</Badge>
                  </td>
                  <td className={TD}>
                    <Badge tone={verdictTone(o.axis, o.new_verdict)}>
                      {o.new_verdict}
                    </Badge>
                  </td>
                  <td className={`${TD} text-xs text-muted`}>{dash(o.rationale)}</td>
                </tr>
              ))}
            </Table>
          </div>
        )}
      </div>

      {r.extraction_edits.length > 0 && (
        <div className="mt-5">
          <p className="text-sm font-bold text-ink">抽出の修正（監査証跡）</p>
          <div className="mt-2">
            <Table head={["種別", "事象", "詳細"]}>
              {r.extraction_edits.map((e, i) => (
                <tr key={`${e.kind}-${e.term}-${i}`}>
                  <td className={`${TD} text-xs`}>
                    {EXTRACTION_EDIT_KIND_LABELS[e.kind] ?? e.kind}
                  </td>
                  <td className={`${TD} font-medium text-ink`}>{e.term}</td>
                  <td className={`${TD} text-xs text-muted`}>{dash(e.detail)}</td>
                </tr>
              ))}
            </Table>
          </div>
        </div>
      )}

      {r.ime_promotions.length > 0 && (
        <div className="mt-5">
          <p className="text-sm font-bold text-ink">
            IMEリストへ昇格したPT（今後の症例に反映）
          </p>
          <div className="mt-2">
            <Table head={["PT名", "PTコード", "状態", "理由"]}>
              {r.ime_promotions.map((p, i) => (
                <tr key={`${p.pt_code}-${i}`}>
                  <td className={`${TD} font-medium text-ink`}>{p.pt_name}</td>
                  <td className={`${TD} font-mono text-xs`}>{p.pt_code}</td>
                  <td className={TD}>
                    <Badge tone={p.status === "追加" ? "good" : "muted"}>
                      {p.status}
                    </Badge>
                  </td>
                  <td className={`${TD} text-xs text-muted`}>{dash(p.rationale)}</td>
                </tr>
              ))}
            </Table>
          </div>
        </div>
      )}

      <button type="button" className={`${BTN_SECONDARY} mt-6`} onClick={onReset}>
        別の症例をレビューする
      </button>
    </Section>
  );
}

// ---------------- switch ----------------

export default function ReviewPanel(
  props:
    | { mode: "draft"; draft: TriageDraft; onFinalized: (r: TriageResult) => void }
    | { mode: "result"; result: TriageResult; onReset: () => void },
) {
  return props.mode === "draft" ? (
    <ReviewForm draft={props.draft} onFinalized={props.onFinalized} />
  ) : (
    <ReviewAudit result={props.result} onReset={props.onReset} />
  );
}
