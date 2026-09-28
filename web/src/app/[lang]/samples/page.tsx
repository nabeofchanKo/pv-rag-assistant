import { readFile } from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";
import { hasLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n";
import { SAMPLE_META } from "@/lib/samples-meta";

// Server component: reads the case files directly, so the page ships no client
// JS and the text cannot drift from what the triage run actually ingests.
export const dynamic = "force-dynamic";

async function readCase(rel: string): Promise<string | null> {
  try {
    return await readFile(path.join(process.cwd(), "public", "samples", rel), "utf-8");
  } catch {
    return null;
  }
}

export default async function SamplesPage({ params }: PageProps<"/[lang]/samples">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const t = getDictionary(lang).samples;

  const cases = await Promise.all(
    SAMPLE_META.map(async (m) => ({
      meta: m,
      text: m.text[lang],
      original: await readCase(m.file),
      // English readers get a reference translation first; the Japanese
      // original stays one click away, labelled as what the pipeline reads.
      translation: lang === "en" ? await readCase(`en/${m.file}`) : null,
    })),
  );

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">{t.kicker}</p>
      <h1 className="mt-2 text-2xl font-bold tracking-tight text-ink">{t.title}</h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
        {t.introBefore}{" "}
        <code className="rounded bg-surface-2 px-1 font-mono text-xs">data/gold/</code>
        {t.introAfter}
      </p>

      <div className="mt-8 space-y-6">
        {cases.map(({ meta, text, original, translation }) => (
          <article
            key={meta.file}
            className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm"
          >
            <header className="border-b border-border p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold text-ink">{text.label}</h2>
                <span className="font-mono text-xs text-muted">{meta.caseId}</span>
                <span
                  className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                    meta.inScope
                      ? "bg-accent-weak text-accent"
                      : "bg-warn-weak text-warn"
                  }`}
                >
                  {meta.inScope ? t.inScope : t.outOfScope}
                </span>
              </div>
              <p className="mt-1 text-sm text-text">{text.role}</p>
              <p className="mt-1 font-mono text-xs text-muted">
                {t.suspectDrug}: {text.drug}
              </p>
            </header>

            <div className="p-5">
              <h3 className="font-mono text-xs uppercase tracking-wider text-muted">
                {t.probesTitle}
              </h3>
              <ol className="mt-3 space-y-3">
                {text.probes.map((p, i) => (
                  <li key={p.title} className="flex gap-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent-weak font-mono text-xs text-accent">
                      {i + 1}
                    </span>
                    <div>
                      <p className="text-sm font-bold text-ink">{p.title}</p>
                      <p className="mt-0.5 text-sm leading-relaxed text-muted">
                        {p.detail}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>

              <div className="mt-5 rounded-lg border-l-2 border-good bg-good-weak/40 px-4 py-3">
                <p className="font-mono text-xs uppercase tracking-wider text-good">
                  {t.expectedTitle}
                </p>
                <p className="mt-1 text-sm leading-relaxed text-text">{text.expected}</p>
              </div>

              {translation && (
                <CaseText summary={t.fullText} file={`en/${meta.file}`} body={translation} />
              )}
              <CaseText
                summary={translation ? t.fullTextOriginal : t.fullText}
                file={meta.file}
                body={original ?? t.readError}
              />
            </div>
          </article>
        ))}
      </div>

      <p className="mt-8 text-xs leading-relaxed text-muted">{t.footer}</p>
    </div>
  );
}

function CaseText({ summary, file, body }: { summary: string; file: string; body: string }) {
  return (
    <details className="mt-4 rounded-lg border border-border bg-surface-2">
      <summary className="cursor-pointer px-4 py-2.5 text-sm font-medium text-ink">
        {summary}
        <span className="ml-2 font-mono text-xs text-muted">{file}</span>
      </summary>
      <pre className="max-h-[32rem] overflow-auto border-t border-border px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap text-text">
        {body}
      </pre>
    </details>
  );
}
