"use client";

import { useEffect, useRef, useState } from "react";
import Spinner from "@/components/Spinner";
import ReviewPanel from "@/components/triage/ReviewPanel";
import TriageSections from "@/components/triage/TriageSections";
import { AXIS_LABELS } from "@/lib/labels";
import type { TriageStartResponse } from "@/lib/types";

type Sample = { file: string; label: string; hint: string };

export default function TriagePage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TriageStartResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Default to demo mode until the server says otherwise, so the upload control
  // is never briefly offered on a deployment that refuses uploads.
  const [demoMode, setDemoMode] = useState(true);
  const [samples, setSamples] = useState<Sample[]>([]);

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
        throw new Error(data?.detail ?? `トリアージ失敗 (HTTP ${res.status})`);
      setResult(data as TriageStartResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function startTriage(f: File) {
    const fd = new FormData();
    fd.append("file", f);
    return run({ method: "POST", body: fd });
  }

  // The BFF reads the bundled sample itself — we only send its name, so no file
  // content is uploaded and the demo cannot be pointed at arbitrary input.
  function startSample(name: string) {
    return run({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sample: name }),
    });
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">
        症例トリアージ
      </p>
      <h1 className="mt-2 text-2xl font-bold tracking-tight text-ink">
        症例を一次評価する
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        症例報告（PDF / テキスト / メール / 画像）を投入すると、自社品判定 → 有害事象抽出 →
        MedDRAコード → 重篤度・既知/未知・因果 → 過去判例の順に、出典付きの評価ドラフトを生成します。
      </p>

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
            ファイルを選択
          </label>
          <span className="min-w-0 flex-1 truncate text-sm text-muted">
            {file ? file.name : "PDF / .txt / .eml / 画像"}
          </span>
          <button
            type="button"
            onClick={() => file && startTriage(file)}
            disabled={!file || loading}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading && <Spinner />}
            トリアージ実行
          </button>
        </div>
        )}

        <div className={demoMode ? "" : "mt-4 border-t border-border pt-4"}>
          <p className="font-mono text-xs uppercase tracking-wider text-muted">
            サンプル症例で試す
          </p>
          {demoMode && (
            <p className="mt-1 text-xs text-muted">
              公開デモのため、実行は同梱のサンプル症例に限定し、回数にも制限を設けています。
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {samples.map((s) => (
              <button
                key={s.file}
                type="button"
                onClick={() => startSample(s.file)}
                disabled={loading}
                className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-left text-sm text-ink transition-colors hover:border-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="font-medium">{s.label}</span>
                <span className="ml-1.5 text-xs text-muted">{s.hint}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {loading && (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-border bg-surface p-6 text-sm text-muted shadow-sm">
          <Spinner className="h-5 w-5 text-accent" />
          解析中… 6ステップ評価（抽出 → MedDRA → 重篤度 → 既知/未知 → 因果 → 判例）
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
                out of scope · 評価対象外
              </p>
              <h2 className="mt-2 text-lg font-bold text-ink">
                自社品が使用されていないため、評価は実行されません
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-text">
                {result.reason}
              </p>
              <p className="mt-3 text-xs text-muted">
                自社品判定を前提条件とするハードゲート（Phase 4g）により、抽出・MedDRA・4判定は実行されていません。
              </p>
              <details className="mt-4 rounded-lg border border-border bg-surface p-4">
                <summary className="cursor-pointer text-sm font-bold text-ink">
                  読み取ったテキスト（出典）
                </summary>
                <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs leading-relaxed text-text">
                  {result.source_text}
                </pre>
              </details>
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
                  {result.status === "awaiting_review"
                    ? "awaiting_review · レビュー待ち"
                    : result.status === "approved"
                      ? "approved · 承認済み"
                      : "rejected · 却下"}
                </span>
                <span className="text-sm text-muted">{result.document_name}</span>
              </div>

              {"escalations" in result && result.escalations.length > 0 && (
                <div className="mb-4 rounded-xl border border-warn/40 bg-warn-weak p-5">
                  <p className="text-sm font-bold text-ink">
                    ⚠️ レビュー要注意（安全側の不確実バンド）— {result.escalations.length}件
                  </p>
                  <ul className="mt-2 space-y-1 text-sm text-text">
                    {result.escalations.map((e, i) => (
                      <li key={`${e.term}-${e.axis}-${i}`}>
                        <span className="font-mono text-xs text-warn">
                          {AXIS_LABELS[e.axis] ?? e.axis}
                        </span>{" "}
                        <span className="font-medium text-ink">{e.term}</span>：
                        {e.verdict} — <span className="text-muted">{e.reason}</span>
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
