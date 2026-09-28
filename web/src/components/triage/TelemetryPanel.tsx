import { useDict } from "@/i18n/LocaleProvider";
import type { RunTelemetry } from "@/lib/types";
import { TD, TH } from "./ui";

// What this run cost and how long it took, per step — measured on the run
// (backend services/telemetry.py), not estimated. Collapsed by default: the
// headline numbers sit in the summary line, the breakdown is one click away.

function usd(v: number | null, unpriced: string): string {
  if (v === null) return unpriced;
  if (v === 0) return "$0";
  if (v < 0.0001) return "<$0.0001";
  return `$${v.toFixed(4)}`;
}

const n = (v: number) => v.toLocaleString("en-US");

export default function TelemetryPanel({ telemetry: t }: { telemetry: RunTelemetry | null }) {
  const dict = useDict();
  if (!t) return null;
  const d = dict.telemetry;
  const sec = d.sec;

  const cached = t.steps.reduce((a, s) => a + s.cached_input_tokens, 0);
  const cachedPct = t.total_input_tokens ? Math.round((cached / t.total_input_tokens) * 100) : 0;
  const stepSum = t.steps.reduce((a, s) => a + s.latency_ms, 0);
  // Guard against a zero-length run (e.g. a gated case measured in ~0 ms).
  const span = Math.max(t.wall_ms, 1);

  return (
    <details className="rounded-xl border border-border bg-surface shadow-sm">
      <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
        {d.title}
        <span className="ml-2 font-mono text-xs font-normal text-muted">
          {usd(t.total_cost_usd, d.unpriced)}
          {!t.cost_complete && d.unpricedSuffix} · {sec(t.wall_ms)} ·{" "}
          {n(t.total_input_tokens + t.total_output_tokens)} tokens
        </span>
      </summary>

      <div className="border-t border-border p-5">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {d.head.map((h, i) => (
                  // column 2 is the timeline
                  <th key={h} className={i === 2 ? `${TH} w-1/3 min-w-32` : TH}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.steps.map((s) => (
                <tr key={s.step}>
                  <td className={`${TD} whitespace-nowrap font-medium text-ink`}>
                    {dict.vocab.step[s.step as keyof typeof dict.vocab.step] ?? s.step}
                  </td>
                  <td className={`${TD} whitespace-nowrap font-mono text-xs text-muted`}>
                    {s.models.length ? s.models.join(", ") : d.noLlm}
                  </td>
                  <td className={`${TD} align-middle`}>
                    {/* start offset → left, duration → width, both as a share
                        of the wall-clock run; overlapping bars = parallel steps */}
                    <div className="relative h-3 rounded-sm bg-surface-2">
                      <div
                        className="absolute inset-y-0 min-w-[2px] rounded-sm bg-accent"
                        style={{
                          left: `${(s.started_ms / span) * 100}%`,
                          width: `${(s.latency_ms / span) * 100}%`,
                        }}
                        title={d.barTitle(sec(s.started_ms), sec(s.latency_ms))}
                      />
                    </div>
                  </td>
                  <td className={`${TD} whitespace-nowrap text-right tabular-nums`}>
                    {sec(s.latency_ms)}
                  </td>
                  <td className={`${TD} whitespace-nowrap text-right tabular-nums text-xs`}>
                    {s.llm_calls ? `${n(s.input_tokens)} / ${n(s.output_tokens)}` : "—"}
                  </td>
                  <td className={`${TD} whitespace-nowrap text-right tabular-nums`}>
                    {usd(s.cost_usd, d.unpriced)}
                  </td>
                </tr>
              ))}
              <tr className="font-bold text-ink">
                <td className={TD} colSpan={3}>
                  {d.total}
                </td>
                <td className={`${TD} text-right tabular-nums`}>{sec(t.wall_ms)}</td>
                <td className={`${TD} whitespace-nowrap text-right tabular-nums text-xs`}>
                  {n(t.total_input_tokens)} / {n(t.total_output_tokens)}
                </td>
                <td className={`${TD} text-right tabular-nums`}>
                  {usd(t.total_cost_usd, d.unpriced)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs leading-relaxed text-muted">
          <li>{d.measured(t.pricing_as_of)}</li>
          {stepSum > t.wall_ms && <li>{d.parallel(sec(stepSum), sec(t.wall_ms))}</li>}
          {cachedPct > 0 && <li>{d.cached(cachedPct)}</li>}
          {!t.cost_complete && <li>{d.unpricedNote}</li>}
          <li>{d.embeddings}</li>
        </ul>
      </div>
    </details>
  );
}
