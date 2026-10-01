"use client";

import { useEffect, useRef, useState } from "react";
import Spinner from "@/components/Spinner";
import CaseBuilder from "@/components/triage/CaseBuilder";
import ReviewPanel from "@/components/triage/ReviewPanel";
import TelemetryPanel from "@/components/triage/TelemetryPanel";
import ReferenceTranslation from "@/components/triage/ReferenceTranslation";
import TriageSections from "@/components/triage/TriageSections";
import { useDict, useLocale, useTerm } from "@/i18n/LocaleProvider";
import { sampleText } from "@/lib/samples-meta";
import type { CaseDraft } from "@/lib/case-builder";
import type { TriageStartResponse } from "@/lib/types";

type Sample = { file: string; label: string; hint: string };

export default function TriagePage() {
  const dict = useDict();
  const t = dict.triage;
  const term = useTerm();
  const locale = useLocale();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TriageStartResponse | null>(null);
  // Which sample produced the result — the out-of-scope response carries no
  // document name, and the reference translation is looked up by it.
  const [ranSample, setRanSample] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Default to demo mode until the server says otherwise, so the upload control
  // is never briefly offered on a deployment that refuses uploads.
  const [demoMode, setDemoMode] = useState(true);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [mode, setMode] = useState<"sample" | "build">("sample");

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((c) => {
        setDemoMode(Boolean(c.demoMode));
        setSamples(c.samples ?? []);
      })
      .catch(() => setSamples([]));
  }, []);

  async function run(init: RequestInit) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/cases/triage", init);
      const data = await res.json();
      if (!res.ok)
        throw new Error(data?.detail ?? t.failed(res.status));
      setResult(data as TriageStartResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function startTriage(f: File) {
    setRanSample(null);
    const fd = new FormData();
    fd.append("file", f);
    return run({ method: "POST", body: fd });
  }

  // The BFF reads the bundled sample itself — we only send its name, so no file
  // content is uploaded and the demo cannot be pointed at arbitrary input.
  function startSample(name: string) {
    setRanSample(name);
    return run({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sample: name }),
    });
  }

  // Likewise the builder sends fields, not a document — the BFF renders the
  // report text server-side after validating them.
  function startBuilt(draft: CaseDraft) {
    setRanSample(null);
    return run({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ build: draft }),
    });
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">
        {t.kicker}
      </p>
      <h1 className="mt-2 text-2xl font-bold tracking-tight text-ink">
        {t.title}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        {t.intro}
      </p>
      {t.languageNote && (
        <p className="mt-3 rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-xs leading-relaxed text-muted">
          {t.languageNote}
        </p>
      )}
      <p className="mt-2 text-xs text-muted">{t.terminologyNote}</p>

      {/* ---- start controls ---- */}
      <section className="mt-8 rounded-xl border border-border bg-surface p-6 shadow-sm">
        {!demoMode && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="cursor-pointer rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm text-ink transition-colors hover:border-accent">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.eml,.png,.jpg,.jpeg,.md"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {t.chooseFile}
          </label>
          <span className="min-w-0 flex-1 truncate text-sm text-muted">
            {file ? file.name : t.fileHint}
          </span>
          <button
            type="button"
            onClick={() => file && startTriage(file)}
            disabled={!file || loading}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading && <Spinner />}
            {t.run}
          </button>
        </div>
        )}

        <div className={demoMode ? "" : "mt-4 border-t border-border pt-4"}>
          <div className="mb-3 inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
            {(
              [
                ["sample", t.modeSample],
                ["build", t.modeBuild],
              ] as const
            ).map(([m, label]) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                  mode === m
                    ? "bg-surface font-medium text-accent shadow-sm"
                    : "text-muted hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === "build" ? (
            <CaseBuilder loading={loading} onRun={startBuilt} />
          ) : (
          <>
          <p className="font-mono text-xs uppercase tracking-wider text-muted">
            {t.trySample}
          </p>
          {demoMode && (
            <p className="mt-1 text-xs text-muted">
              {t.demoNote}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {samples.map((s) => {
              // The server's list is the allowlist; the words come from the
              // catalogue in the reader's language.
              const st = sampleText(s.file, locale);
              return (
              <button
                key={s.file}
                type="button"
                onClick={() => startSample(s.file)}
                disabled={loading}
                className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-left text-sm text-ink transition-colors hover:border-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="font-medium">{st?.label ?? s.label}</span>
                <span className="ml-1.5 text-xs text-muted">{st?.hint ?? s.hint}</span>
              </button>
              );
            })}
          </div>
          </>
          )}
        </div>
      </section>

      {loading && (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-border bg-surface p-6 text-sm text-muted shadow-sm">
          <Spinner className="h-5 w-5 text-accent" />
          {t.running}
        </div>
      )}

      {error && (
        <p className="mt-6 rounded-lg border border-danger/40 bg-danger-weak px-4 py-3 text-sm text-danger">
          {error}
        </p>
      )}

      {result && !loading && (
        <div className="mt-8">
          {result.status === "out_of_scope" ? (
            <section className="rounded-xl border border-warn/40 bg-warn-weak p-6">
              <p className="font-mono text-xs uppercase tracking-widest text-warn">
                {t.oosKicker}
              </p>
              <h2 className="mt-2 text-lg font-bold text-ink">
                {t.oosTitle}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-text">
                {result.reason}
              </p>
              <p className="mt-3 text-xs text-muted">
                {t.oosGate}
              </p>
              <div className="mt-4">
                <TelemetryPanel telemetry={result.telemetry} />
              </div>
              <details className="mt-4 rounded-lg border border-border bg-surface p-4">
                <summary className="cursor-pointer text-sm font-bold text-ink">
                  {t.sourceText}
                </summary>
                <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs leading-relaxed text-text">
                  {result.source_text}
                </pre>
              </details>
              {ranSample && (
                <div className="mt-4">
                  <ReferenceTranslation documentName={ranSample} />
                </div>
              )}
            </section>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <span
                  className={`rounded-md px-2 py-1 font-mono text-xs ${
                    result.status === "awaiting_review"
                      ? "bg-accent-weak text-accent"
                      : result.status === "approved"
                        ? "bg-good-weak text-good"
                        : "bg-danger-weak text-danger"
                  }`}
                >
                  {t.status[result.status]}
                </span>
                <span className="text-sm text-muted">{result.document_name}</span>
              </div>

              {"escalations" in result && result.escalations.length > 0 && (
                <div className="mb-4 rounded-xl border border-warn/40 bg-warn-weak p-5">
                  <p className="text-sm font-bold text-ink">
                    {t.escalations(result.escalations.length)}
                  </p>
                  <ul className="mt-2 space-y-1 text-sm text-text">
                    {result.escalations.map((e, i) => (
                      <li key={`${e.term}-${e.axis}-${i}`}>
                        <span className="font-mono text-xs text-warn">
                          {dict.vocab.axis[e.axis] ?? e.axis}
                        </span>{" "}
                        <span className="font-medium text-ink">{e.term}</span>:{" "}
                        {term(e.verdict)} — <span className="text-muted">{e.reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <TriageSections
                data={result}
                review={result.status === "awaiting_review" ? null : result.review}
              />

              <div className="mt-4">
                {result.status === "awaiting_review" ? (
                  <ReviewPanel
                    mode="draft"
                    draft={result}
                    onFinalized={(r) => setResult(r)}
                  />
                ) : (
                  <ReviewPanel
                    mode="result"
                    result={result}
                    onReset={() => setResult(null)}
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
