import { readFile } from "node:fs/promises";
import path from "node:path";
import { SAMPLE_META } from "@/lib/samples-meta";

// Server component: reads the case files directly, so the page ships no client
// JS and the text cannot drift from what the triage run actually ingests.
export const dynamic = "force-dynamic";

async function readCase(file: string): Promise<string> {
  try {
    return await readFile(path.join(process.cwd(), "public", "samples", file), "utf-8");
  } catch {
    return "（症例ファイルを読み込めませんでした）";
  }
}

export default async function SamplesPage() {
  const cases = await Promise.all(
    SAMPLE_META.map(async (m) => ({ meta: m, text: await readCase(m.file) })),
  );

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">
        サンプル症例
      </p>
      <h1 className="mt-2 text-2xl font-bold tracking-tight text-ink">
        何を検証するための症例か
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
        デモで実行できる症例は、それぞれ特定の挙動を検証するために書き起こした合成症例です（実患者データは含みません）。
        期待される判定は{" "}
        <code className="rounded bg-surface-2 px-1 font-mono text-xs">data/gold/</code>{" "}
        に正解として固定してあり、評価ハーネスがこれに対して採点します。
      </p>

      <div className="mt-8 space-y-6">
        {cases.map(({ meta, text }) => (
          <article
            key={meta.file}
            className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm"
          >
            <header className="border-b border-border p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold text-ink">{meta.label}</h2>
                <span className="font-mono text-xs text-muted">{meta.caseId}</span>
                <span
                  className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                    meta.inScope
                      ? "bg-accent-weak text-accent"
                      : "bg-warn-weak text-warn"
                  }`}
                >
                  {meta.inScope ? "評価対象" : "評価対象外"}
                </span>
              </div>
              <p className="mt-1 text-sm text-text">{meta.role}</p>
              <p className="mt-1 font-mono text-xs text-muted">
                被疑薬: {meta.drug}
              </p>
            </header>

            <div className="p-5">
              <h3 className="font-mono text-xs uppercase tracking-wider text-muted">
                この症例で検証したいこと
              </h3>
              <ol className="mt-3 space-y-3">
                {meta.probes.map((p, i) => (
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
                  期待される判定（gold）
                </p>
                <p className="mt-1 text-sm leading-relaxed text-text">
                  {meta.expected}
                </p>
              </div>

              <details className="mt-4 rounded-lg border border-border bg-surface-2">
                <summary className="cursor-pointer px-4 py-2.5 text-sm font-medium text-ink">
                  症例の全文を見る
                  <span className="ml-2 font-mono text-xs text-muted">
                    {meta.file}
                  </span>
                </summary>
                <pre className="max-h-[32rem] overflow-auto border-t border-border px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap text-text">
                  {text}
                </pre>
              </details>
            </div>
          </article>
        ))}
      </div>

      <p className="mt-8 text-xs leading-relaxed text-muted">
        すべて本プロジェクト用に作成した合成症例で、実際の患者データは含まれません。
        添付文書も同様に、実在の製品を模した架空のものです。
      </p>
    </div>
  );
}
