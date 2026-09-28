"use client";

import { useEffect, useState } from "react";
import { useDict, useLocale } from "@/i18n/LocaleProvider";
import { SAMPLE_FILES } from "@/lib/samples-meta";

// For an English reader who ran a bundled sample: its English reference
// translation (public/samples/en/), under the Japanese text the pipeline read.
// Nothing for other cases or in Japanese — there is no translation to show,
// and none is generated (that would be another model call).

export default function ReferenceTranslation({ documentName }: { documentName: string }) {
  const t = useDict().triage;
  const locale = useLocale();
  const [text, setText] = useState<string | null>(null);
  const available = locale === "en" && SAMPLE_FILES.includes(documentName);

  useEffect(() => {
    if (!available) return;
    let cancelled = false;
    fetch(`/samples/en/${encodeURIComponent(documentName)}`)
      .then((r) => (r.ok ? r.text() : null))
      .then((body) => {
        if (!cancelled) setText(body);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [available, documentName]);

  if (!available || !text) return null;
  return (
    <details className="rounded-xl border border-border bg-surface shadow-sm">
      <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
        {t.referenceTranslation}
        <span className="ml-2 text-xs font-normal text-muted">{t.referenceTranslationNote}</span>
      </summary>
      <pre className="max-h-96 overflow-auto border-t border-border p-5 text-xs leading-relaxed whitespace-pre-wrap text-text">
        {text}
      </pre>
    </details>
  );
}
