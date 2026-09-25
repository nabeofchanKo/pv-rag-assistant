"use client";

import { useState } from "react";
import Link from "next/link";
import { CASE_STUDY, type Lang } from "@/lib/case-study";

// Renders **bold** spans without pulling in a markdown dependency for the one
// emphasis style this content uses.
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-bold text-ink">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

export default function AboutPage() {
  const [lang, setLang] = useState<Lang>("ja");
  const c = CASE_STUDY[lang];

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <p className="font-mono text-xs uppercase tracking-widest text-accent">
          {c.kicker}
        </p>
        <div className="inline-flex shrink-0 rounded-lg border border-border bg-surface-2 p-0.5">
          {(["ja", "en"] as const).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLang(l)}
              className={`rounded-md px-2.5 py-1 font-mono text-xs transition-colors ${
                lang === l
                  ? "bg-surface font-medium text-accent shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {l === "ja" ? "日本語" : "EN"}
            </button>
          ))}
        </div>
      </div>

      <h1 className="mt-2 text-2xl font-bold leading-tight tracking-tight text-ink sm:text-3xl">
        {c.title}
      </h1>
      <p className="mt-4 text-base leading-relaxed text-text">{c.lede}</p>

      <Link
        href="/triage"
        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white"
      >
        {c.ctaLabel} →
      </Link>

      {/* problem */}
      <section className="mt-12">
        <h2 className="text-lg font-bold text-ink">{c.problem.heading}</h2>
        <div className="mt-3 space-y-3">
          {c.problem.body.map((p, i) => (
            <p key={i} className="text-sm leading-relaxed text-text">
              <Rich text={p} />
            </p>
          ))}
        </div>
      </section>

      {/* decisions */}
      <section className="mt-12">
        <h2 className="text-lg font-bold text-ink">{c.decisionsHeading}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">{c.decisionsIntro}</p>
        <div className="mt-5 space-y-3">
          {c.decisions.map((d, i) => (
            <article
              key={d.title}
              className="rounded-xl border border-border bg-surface p-5 shadow-sm"
            >
              <h3 className="flex gap-3 text-sm font-bold text-ink">
                <span className="font-mono text-accent">
                  {String(i + 1).padStart(2, "0")}
                </span>
                {d.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-text">
                <Rich text={d.body} />
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* evidence */}
      <section className="mt-12">
        <h2 className="text-lg font-bold text-ink">{c.evidenceHeading}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">{c.evidenceIntro}</p>
        <div className="mt-5 grid grid-cols-2 gap-4 rounded-xl border border-border bg-surface p-5 shadow-sm sm:grid-cols-4">
          {c.metrics.map((m) => (
            <div key={m.label}>
              <div
                className={`text-2xl font-bold tabular-nums ${
                  m.tone === "good" ? "text-good" : "text-ink"
                }`}
              >
                {m.value}
              </div>
              <div className="mt-1 text-xs leading-snug text-muted">{m.label}</div>
            </div>
          ))}
        </div>

        {/* limitations sit immediately under the numbers on purpose */}
        <div className="mt-4 rounded-xl border-l-2 border-warn bg-warn-weak/40 p-5">
          <h3 className="text-sm font-bold text-ink">{c.limits.heading}</h3>
          <div className="mt-2 space-y-2">
            {c.limits.body.map((p, i) => (
              <p key={i} className="text-sm leading-relaxed text-text">
                <Rich text={p} />
              </p>
            ))}
          </div>
        </div>
      </section>

      {/* how it was built */}
      <section className="mt-12">
        <h2 className="text-lg font-bold text-ink">{c.building.heading}</h2>
        <div className="mt-3 space-y-3">
          {c.building.body.map((p, i) => (
            <p key={i} className="text-sm leading-relaxed text-text">
              <Rich text={p} />
            </p>
          ))}
        </div>
      </section>

      {/* next */}
      <section className="mt-12">
        <h2 className="text-lg font-bold text-ink">{c.next.heading}</h2>
        <ul className="mt-3 space-y-2">
          {c.next.body.map((p, i) => (
            <li key={i} className="flex gap-3 text-sm leading-relaxed text-text">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              <span>{p}</span>
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-12 border-t border-border pt-5 text-xs leading-relaxed text-muted">
        {c.footer}
      </p>
    </div>
  );
}
