import { STEP_LABELS } from "@/lib/labels";
import type { RunTelemetry } from "@/lib/types";
import { TD, TH } from "./ui";

// What this run cost and how long it took, per step — measured on the run
// (backend services/telemetry.py), not estimated. Collapsed by default: the
// headline numbers sit in the summary line, the breakdown is one click away.

function usd(v: number | null): string {
  if (v === null) return "価格未登録";
  if (v === 0) return "$0";
  if (v < 0.0001) return "<$0.0001";
  return `$${v.toFixed(4)}`;
}

const sec = (ms: number) => `${(ms / 1000).toFixed(1)}秒`;
const n = (v: number) => v.toLocaleString("en-US");

export default function TelemetryPanel({ telemetry: t }: { telemetry: RunTelemetry | null }) {
  if (!t) return null;

  const cached = t.steps.reduce((a, s) => a + s.cached_input_tokens, 0);
  const cachedPct = t.total_input_tokens ? Math.round((cached / t.total_input_tokens) * 100) : 0;
  const stepSum = t.steps.reduce((a, s) => a + s.latency_ms, 0);
  // Guard against a zero-length run (e.g. a gated case measured in ~0 ms).
  const span = Math.max(t.wall_ms, 1);

  return (
    <details className="rounded-xl border border-border bg-surface shadow-sm">
      <summary className="cursor-pointer p-5 text-sm font-bold text-ink">
        コスト・処理時間
        <span className="ml-2 font-mono text-xs font-normal text-muted">
          {usd(t.total_cost_usd)}
          {!t.cost_complete && "＋未登録分"} · {sec(t.wall_ms)} ·{" "}
          {n(t.total_input_tokens + t.total_output_tokens)} tokens
        </span>
      </summary>

      <div className="border-t border-border p-5">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {["ステップ", "モデル", "タイムライン", "時間", "入力 / 出力", "費用"].map((h) => (
                  <th key={h} className={h === "タイムライン" ? `${TH} w-1/3 min-w-32` : TH}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.steps.map((s) => (
                <tr key={s.step}>
                  <td className={`${TD} whitespace-nowrap font-medium text-ink`}>
                    {STEP_LABELS[s.step] ?? s.step}
                  </td>
                  <td className={`${TD} whitespace-nowrap font-mono text-xs text-muted`}>
                    {s.models.length ? s.models.join(", ") : "—（LLMなし）"}
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
                        title={`開始 +${sec(s.started_ms)} ／ ${sec(s.latency_ms)}`}
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
                    {usd(s.cost_usd)}
                  </td>
                </tr>
              ))}
              <tr className="font-bold text-ink">
                <td className={TD} colSpan={3}>
                  合計（待ち時間）
                </td>
                <td className={`${TD} text-right tabular-nums`}>{sec(t.wall_ms)}</td>
                <td className={`${TD} whitespace-nowrap text-right tabular-nums text-xs`}>
                  {n(t.total_input_tokens)} / {n(t.total_output_tokens)}
                </td>
                <td className={`${TD} text-right tabular-nums`}>{usd(t.total_cost_usd)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs leading-relaxed text-muted">
          <li>
            この実行で実測した値です（推定ではありません）。価格は {t.pricing_as_of} 時点の OpenAI
            標準料金で計算しています。
          </li>
          {stepSum > t.wall_ms && (
            <li>
              既知/未知・因果関係・MedDRA は並列に実行されるため、各ステップの時間の合計（
              {sec(stepSum)}）は実際の待ち時間（{sec(t.wall_ms)}）より長くなります。
            </li>
          )}
          {cachedPct > 0 && (
            <li>
              入力の {cachedPct}% はプロンプトキャッシュに一致し、割引単価で課金されています。
              同じ症例を初めて実行するときは、この割合が下がり費用は上がります。
            </li>
          )}
          {!t.cost_complete && (
            <li>価格表にないモデル（ローカルモデル等）の分は合計に含まれていません。</li>
          )}
          <li>検索用の埋め込み（添付文書・MedDRA）は含みません。この規模では 1 セント未満です。</li>
        </ul>
      </div>
    </details>
  );
}
