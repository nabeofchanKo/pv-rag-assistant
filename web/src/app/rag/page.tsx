"use client";

import { useEffect, useRef, useState } from "react";
import type { QueryResponse, UploadResponse } from "@/lib/types";

function Spinner() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export default function RagPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [indexed, setIndexed] = useState<UploadResponse[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<QueryResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  // Fail closed: assume the demo's upload restriction until the server says otherwise.
  const [demoMode, setDemoMode] = useState(true);
  const [samples, setSamples] = useState<{ file: string; label: string }[]>([]);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((c) => {
        setDemoMode(Boolean(c.demoMode));
        setSamples(c.samples ?? []);
      })
      .catch(() => setSamples([]));
  }, []);

  async function indexPayload(init: RequestInit) {
    setUploading(true);
    setUploadError(null);
    setUploadMsg(null);
    try {
      const res = await fetch("/api/documents/upload", init);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? `索引化に失敗しました (HTTP ${res.status})`);
      const up = data as UploadResponse;
      setUploadMsg(`${up.document_name}：${up.chunks_added} チャンクを索引に追加しました。`);
      setIndexed((prev) => [
        up,
        ...prev.filter((d) => d.document_name !== up.document_name),
      ]);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  // The BFF reads the bundled sample itself — only its name is sent.
  function indexSample(name: string) {
    return indexPayload({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sample: name }),
    });
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/documents/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? `アップロード失敗 (HTTP ${res.status})`);
      const up = data as UploadResponse;
      setUploadMsg(`${up.document_name}：${up.chunks_added} チャンクを索引に追加しました。`);
      setIndexed((prev) => [
        up,
        ...prev.filter((d) => d.document_name !== up.document_name),
      ]);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleAsk() {
    const q = question.trim();
    if (!q) return;
    setAsking(true);
    setQueryError(null);
    setAnswer(null);
    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: q, top_k: 5 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? `検索失敗 (HTTP ${res.status})`);
      setAnswer(data as QueryResponse);
    } catch (e) {
      setQueryError(e instanceof Error ? e.message : String(e));
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">RAG Q&amp;A</p>
      <h1 className="mt-2 text-2xl font-bold tracking-tight text-ink">
        報告書に、出典付きで質問する
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        PV 報告書（PDF / テキスト / メール）をアップロードして索引化し、内容について質問します。
        回答は検索された文脈のみに基づき、出典（文書名・ページ）付きで返ります。
      </p>

      {/* ---- ① Upload ---- */}
      <section className="mt-8 rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="text-sm font-bold text-ink">① 文書を索引化</h2>
        {demoMode && (
          <>
            <p className="mt-1 text-xs text-muted">
              公開デモのためアップロードは無効です。同梱のサンプル症例を索引化してお試しください。
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {samples.map((s) => (
                <button
                  key={s.file}
                  type="button"
                  onClick={() => indexSample(s.file)}
                  disabled={uploading}
                  className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {s.label} を索引化
                </button>
              ))}
            </div>
          </>
        )}
        {!demoMode && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="cursor-pointer rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm text-ink transition-colors hover:border-accent">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.eml,.png"
              className="hidden"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setUploadMsg(null);
                setUploadError(null);
              }}
            />
            ファイルを選択
          </label>
          <span className="min-w-0 flex-1 truncate text-sm text-muted">
            {file ? file.name : "PDF / .txt / .eml / .png"}
          </span>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!file || uploading}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          >
            {uploading && <Spinner />}
            {uploading ? "索引化中…" : "アップロード＆索引化"}
          </button>
        </div>
        )}

        {uploadMsg && (
          <p className="mt-3 rounded-lg border border-good/40 bg-good-weak px-3 py-2 text-sm text-good">
            {uploadMsg}
          </p>
        )}
        {uploadError && (
          <p className="mt-3 rounded-lg border border-danger/40 bg-danger-weak px-3 py-2 text-sm text-danger">
            {uploadError}
          </p>
        )}
        {indexed.length > 0 && (
          <div className="mt-4 border-t border-border pt-3">
            <p className="font-mono text-xs uppercase tracking-wider text-muted">
              索引済み
            </p>
            <ul className="mt-2 space-y-1">
              {indexed.map((d) => (
                <li key={d.document_name} className="text-sm text-text">
                  <span className="font-medium text-ink">{d.document_name}</span>
                  <span className="text-muted"> — {d.chunks_added} チャンク</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* ---- ② Ask ---- */}
      <section className="mt-6 rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="text-sm font-bold text-ink">② 質問する</h2>
        {indexed.length === 0 && (
          <p className="mt-2 text-xs text-muted">
            ※ まず文書をアップロードしてください（質問はアップロード済みの文書に対して検索されます）。
          </p>
        )}
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleAsk();
          }}
          rows={3}
          placeholder="例：報告された有害事象と、その転帰を教えてください。"
          className="mt-3 w-full resize-y rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink outline-none placeholder:text-muted focus:border-accent"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className="font-mono text-xs text-muted">⌘/Ctrl + Enter で送信</span>
          <button
            type="button"
            onClick={handleAsk}
            disabled={!question.trim() || asking}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          >
            {asking && <Spinner />}
            {asking ? "検索中…" : "質問する"}
          </button>
        </div>
        {queryError && (
          <p className="mt-3 rounded-lg border border-danger/40 bg-danger-weak px-3 py-2 text-sm text-danger">
            {queryError}
          </p>
        )}
      </section>

      {/* ---- Answer ---- */}
      {answer && (
        <section className="mt-6 rounded-xl border border-border bg-surface p-6 shadow-sm">
          <h2 className="text-sm font-bold text-ink">回答</h2>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text">
            {answer.answer}
          </p>

          {answer.sources.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <p className="font-mono text-xs uppercase tracking-wider text-muted">
                出典 {answer.sources.length} 件
              </p>
              <div className="mt-2 space-y-2">
                {answer.sources.map((s, i) => (
                  <details
                    key={`${s.document_name}-${s.chunk_index}-${i}`}
                    className="group rounded-lg border border-border bg-surface-2 px-3 py-2"
                  >
                    <summary className="cursor-pointer list-none text-sm text-ink marker:content-none">
                      <span className="font-mono text-xs text-accent">
                        {s.document_name} · p.{s.page_number}
                      </span>
                      <span className="ml-2 text-xs text-muted group-open:hidden">
                        （クリックで本文）
                      </span>
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-text">
                      {s.text}
                    </p>
                  </details>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
