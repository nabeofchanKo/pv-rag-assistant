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
import { useDict, useTerm } from "@/i18n/LocaleProvider";
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
  const t = useDict().builder;
  const term = useTerm();
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
        <p className="max-w-xl text-xs leading-relaxed text-muted">{t.intro}</p>
        <button
          type="button"
          className={`${BTN_SECONDARY} px-3 py-1.5 text-xs`}
          onClick={() => setDraft(PRESET_DRAFT)}
          disabled={loading}
        >
          {t.loadExample}
        </button>
      </div>
      {t.inputNote && (
        <p className="mt-3 rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs leading-relaxed text-muted">
          {t.inputNote}
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Field label={t.drug}>
          <select
            className={INPUT_CLASS}
            value={draft.drug}
            onChange={(e) => set({ drug: e.target.value })}
          >
            {BUILDER_DRUGS.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
                {d.ownCompany ? "" : t.notOwn}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t.age}>
          <input
            className={INPUT_CLASS}
            placeholder={t.agePlaceholder}
            value={draft.age}
            onChange={(e) => set({ age: e.target.value })}
          />
        </Field>
        <Field label={t.sex}>
          <select
            className={INPUT_CLASS}
            value={draft.sex}
            onChange={(e) => set({ sex: e.target.value })}
          >
            {SEX_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {term(o)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t.startDate}>
          <input
            className={INPUT_CLASS}
            placeholder="2026-01-10"
            value={draft.startDate}
            onChange={(e) => set({ startDate: e.target.value })}
          />
        </Field>
        <Field label={t.endDate}>
          <input
            className={INPUT_CLASS}
            placeholder="2026-02-02"
            value={draft.endDate}
            onChange={(e) => set({ endDate: e.target.value })}
          />
        </Field>
        <Field label={t.reportedCausality}>
          <select
            className={INPUT_CLASS}
            value={draft.reportedCausality}
            onChange={(e) => set({ reportedCausality: e.target.value })}
          >
            {REPORTED_CAUSALITY_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {term(o)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {!drug?.ownCompany && (
        <p className="mt-3 rounded-lg border border-warn/40 bg-warn-weak px-3 py-2 text-xs text-warn">
          {t.notOwnWarning}
        </p>
      )}

      {/* events */}
      <div className="mt-5 border-t border-border pt-4">
        <p className="text-sm font-bold text-ink">{t.eventsTitle}</p>
        <p className="mt-1 text-xs text-muted">{t.eventsNote}</p>
        <div className="mt-3 space-y-2">
          {draft.events.map((ev, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_9rem_8rem_8rem_2rem]">
              <input
                aria-label={t.eventLabel(i + 1, t.eventFields.name)}
                className={INPUT_CLASS}
                placeholder={t.termPlaceholder}
                value={ev.term}
                onChange={(e) => setEvent(i, { term: e.target.value })}
              />
              <input
                aria-label={t.eventLabel(i + 1, t.eventFields.onset)}
                className={INPUT_CLASS}
                placeholder={t.onsetPlaceholder}
                value={ev.onset}
                onChange={(e) => setEvent(i, { onset: e.target.value })}
              />
              <select
                aria-label={t.eventLabel(i + 1, t.eventFields.outcome)}
                className={INPUT_CLASS}
                value={ev.outcome}
                onChange={(e) => setEvent(i, { outcome: e.target.value })}
              >
                {OUTCOME_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {term(o)}
                  </option>
                ))}
              </select>
              <select
                aria-label={t.eventLabel(i + 1, t.eventFields.ser)}
                className={INPUT_CLASS}
                value={ev.seriousness}
                onChange={(e) => setEvent(i, { seriousness: e.target.value })}
              >
                {REPORTED_SERIOUSNESS_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {term(o)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label={t.eventRemove(i + 1)}
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
          {t.addEvent}
        </button>
      </div>

      {/* narrative */}
      <div className="mt-5 border-t border-border pt-4">
        <label className="block">
          <span className="text-sm font-bold text-ink">{t.narrativeTitle}</span>
          <p className="mt-1 text-xs text-muted">{t.narrativeNote}</p>
          <textarea
            className={`${INPUT_CLASS} mt-2 min-h-40 resize-y`}
            maxLength={BUILDER_LIMITS.maxNarrative}
            placeholder={t.narrativePlaceholder}
            value={draft.narrative}
            onChange={(e) => set({ narrative: e.target.value })}
          />
        </label>
        <p className="mt-1 text-right font-mono text-xs text-muted">
          {draft.narrative.length} / {BUILDER_LIMITS.maxNarrative}
        </p>
        {t.exampleTranslation && draft.narrative === PRESET_DRAFT.narrative && (
          <details className="mt-2 rounded-lg border border-border bg-surface-2" open>
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink">
              {t.exampleTranslationTitle}
            </summary>
            <p className="border-t border-border px-3 py-2 text-xs leading-relaxed whitespace-pre-line text-muted">
              {t.exampleTranslation}
            </p>
          </details>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={BTN_PRIMARY}
          disabled={!canRun}
          onClick={() => onRun(draft)}
        >
          {loading && <Spinner />}
          {t.run}
        </button>
        <button
          type="button"
          className={`${BTN_SECONDARY} text-xs`}
          disabled={loading}
          onClick={() => setDraft(EMPTY_DRAFT)}
        >
          {t.clear}
        </button>
      </div>
    </div>
  );
}
