"use client";

import { useState } from "react";
import Spinner from "@/components/Spinner";
import {
  BUILDER_DRUGS,
  BUILDER_LIMITS,
  type CaseDraft,
  EMPTY_DRAFT,
  EMPTY_EVENT,
  OUTCOME_OPTIONS,
  PRESET_DRAFT,
  REPORTED_CAUSALITY_OPTIONS,
  REPORTED_SERIOUSNESS_OPTIONS,
  SEX_OPTIONS,
} from "@/lib/case-builder";
import { BTN_PRIMARY, BTN_SECONDARY, INPUT_CLASS } from "./ui";

// Compose a case by hand to probe a specific behaviour. Only the fields travel
// to the server — the report text is rendered there (see lib/case-builder.ts).

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-muted">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

export default function CaseBuilder({
  loading,
  onRun,
}: {
  loading: boolean;
  onRun: (draft: CaseDraft) => void;
}) {
  const [draft, setDraft] = useState<CaseDraft>(EMPTY_DRAFT);

  const set = (patch: Partial<CaseDraft>) => setDraft((d) => ({ ...d, ...patch }));
  const setEvent = (i: number, patch: Partial<CaseDraft["events"][number]>) =>
    setDraft((d) => ({
      ...d,
      events: d.events.map((e, j) => (j === i ? { ...e, ...patch } : e)),
    }));

  const drug = BUILDER_DRUGS.find((d) => d.name === draft.drug);
  const canRun = draft.events.some((e) => e.term.trim()) && !loading;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-xl text-xs leading-relaxed text-muted">
          報告内容と経過を組み立てて、評価がどう動くかを確かめられます。
          たとえば「報告は非重篤のめまい、ただし経過に転倒・骨折・入院の記載」とすると、
          企業評価が入院を根拠に重篤へ引き上げられるかを試せます。
        </p>
        <button
          type="button"
          className={`${BTN_SECONDARY} px-3 py-1.5 text-xs`}
          onClick={() => setDraft(PRESET_DRAFT)}
          disabled={loading}
        >
          この例を読み込む
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Field label="被疑薬">
          <select
            className={INPUT_CLASS}
            value={draft.drug}
            onChange={(e) => set({ drug: e.target.value })}
          >
            {BUILDER_DRUGS.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
                {d.ownCompany ? "" : "（自社品ではない）"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="年齢">
          <input
            className={INPUT_CLASS}
            placeholder="例：78歳"
            value={draft.age}
            onChange={(e) => set({ age: e.target.value })}
          />
        </Field>
        <Field label="性別">
          <select
            className={INPUT_CLASS}
            value={draft.sex}
            onChange={(e) => set({ sex: e.target.value })}
          >
            {SEX_OPTIONS.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </Field>
        <Field label="投与開始日">
          <input
            className={INPUT_CLASS}
            placeholder="2026-01-10"
            value={draft.startDate}
            onChange={(e) => set({ startDate: e.target.value })}
          />
        </Field>
        <Field label="投与終了日">
          <input
            className={INPUT_CLASS}
            placeholder="2026-02-02"
            value={draft.endDate}
            onChange={(e) => set({ endDate: e.target.value })}
          />
        </Field>
        <Field label="報告者による因果関係">
          <select
            className={INPUT_CLASS}
            value={draft.reportedCausality}
            onChange={(e) => set({ reportedCausality: e.target.value })}
          >
            {REPORTED_CAUSALITY_OPTIONS.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </Field>
      </div>

      {!drug?.ownCompany && (
        <p className="mt-3 rounded-lg border border-warn/40 bg-warn-weak px-3 py-2 text-xs text-warn">
          この薬剤は自社製品マスタに存在しないため、評価は実行されず「対象外」で終了します（ハードゲートの確認用）。
        </p>
      )}

      {/* events */}
      <div className="mt-5 border-t border-border pt-4">
        <p className="text-sm font-bold text-ink">報告された有害事象</p>
        <p className="mt-1 text-xs text-muted">
          ここは「報告どおり」の転記です。企業評価（重篤度・因果・既知/未知）は経過文とあわせてシステムが判定します。
        </p>
        <div className="mt-3 space-y-2">
          {draft.events.map((ev, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_9rem_8rem_8rem_2rem]">
              <input
                aria-label={`事象${i + 1} の名称`}
                className={INPUT_CLASS}
                placeholder="事象名（例：浮動性めまい）"
                value={ev.term}
                onChange={(e) => setEvent(i, { term: e.target.value })}
              />
              <input
                aria-label={`事象${i + 1} の発現日`}
                className={INPUT_CLASS}
                placeholder="発現日"
                value={ev.onset}
                onChange={(e) => setEvent(i, { onset: e.target.value })}
              />
              <select
                aria-label={`事象${i + 1} の転帰`}
                className={INPUT_CLASS}
                value={ev.outcome}
                onChange={(e) => setEvent(i, { outcome: e.target.value })}
              >
                {OUTCOME_OPTIONS.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
              <select
                aria-label={`事象${i + 1} の報告重篤度`}
                className={INPUT_CLASS}
                value={ev.seriousness}
                onChange={(e) => setEvent(i, { seriousness: e.target.value })}
              >
                {REPORTED_SERIOUSNESS_OPTIONS.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`事象${i + 1} を削除`}
                className="rounded px-2 text-sm text-muted hover:text-danger disabled:opacity-30"
                disabled={draft.events.length === 1}
                onClick={() =>
                  setDraft((d) => ({
                    ...d,
                    events: d.events.filter((_, j) => j !== i),
                  }))
                }
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          className={`${BTN_SECONDARY} mt-2 px-3 py-1.5 text-xs`}
          disabled={draft.events.length >= BUILDER_LIMITS.maxEvents || loading}
          onClick={() =>
            setDraft((d) => ({ ...d, events: [...d.events, { ...EMPTY_EVENT }] }))
          }
        >
          ＋ 事象を追加
        </button>
      </div>

      {/* narrative */}
      <div className="mt-5 border-t border-border pt-4">
        <label className="block">
          <span className="text-sm font-bold text-ink">症例経過</span>
          <p className="mt-1 text-xs text-muted">
            ここが判定の勝負どころです。報告欄に書かれていない事実（転倒、骨折、入院、処置など）を経過に書くと、
            企業評価がそれを拾えるかどうかを確認できます。
          </p>
          <textarea
            className={`${INPUT_CLASS} mt-2 min-h-40 resize-y`}
            maxLength={BUILDER_LIMITS.maxNarrative}
            placeholder="時系列で経過を記載してください。"
            value={draft.narrative}
            onChange={(e) => set({ narrative: e.target.value })}
          />
        </label>
        <p className="mt-1 text-right font-mono text-xs text-muted">
          {draft.narrative.length} / {BUILDER_LIMITS.maxNarrative}
        </p>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={BTN_PRIMARY}
          disabled={!canRun}
          onClick={() => onRun(draft)}
        >
          {loading && <Spinner />}
          この症例をトリアージ
        </button>
        <button
          type="button"
          className={`${BTN_SECONDARY} text-xs`}
          disabled={loading}
          onClick={() => setDraft(EMPTY_DRAFT)}
        >
          クリア
        </button>
      </div>
    </div>
  );
}
