import type { ReactNode } from "react";
import type { Tone } from "@/lib/labels";

// Shared presentational primitives for the triage screens.

const TONE_CLASS: Record<Tone, string> = {
  danger: "bg-danger-weak text-danger",
  warn: "bg-warn-weak text-warn",
  good: "bg-good-weak text-good",
  muted: "bg-surface-2 text-muted",
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

export function Section({
  num,
  title,
  caption,
  children,
}: {
  num: string;
  title: string;
  caption?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-sm">
      <h3 className="flex items-baseline gap-2 text-sm font-bold text-ink">
        <span className="font-mono text-accent">{num}</span>
        {title}
      </h3>
      {caption && (
        <p className="mt-1 text-xs leading-relaxed text-muted">{caption}</p>
      )}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export const TH =
  "border-b border-border px-3 py-2 text-left text-xs font-medium text-muted whitespace-nowrap";
export const TD = "border-b border-border px-3 py-2 align-top";

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} className={TH}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export const dash = (v: string | null | undefined) => (v && v.trim() ? v : "—");

// Form controls
export const INPUT_CLASS =
  "w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-sm text-ink outline-none placeholder:text-muted focus:border-accent";

export const BTN_PRIMARY =
  "inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40";

export const BTN_SECONDARY =
  "inline-flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-accent disabled:cursor-not-allowed disabled:opacity-40";
