import type { TriageContent } from "@/lib/types";
import {
  AXIS_LABELS,
  INFLUENCE_SOURCE_LABELS,
  SOURCE_LABELS,
  counts,
  reportedIsSerious,
  verdictTone,
} from "@/lib/labels";
import { Badge, Section, TD, Table, dash } from "./ui";

// ---- the 8-section triage view (read-only; shared by draft & result) ----

export default function TriageSections({ data }: { data: TriageContent }) {
  const pm = data.product_match;
  const ext = data.extraction;
  const meddra = data.meddra ?? [];

  return (
    <div className="space-y-4">
      {/* ① 自社品判定 */}
      <Section num="①" title="自社品判定">
        {pm.is_company_product_present ? (
          <div>
            <Badge tone="good">
              自社品該当あり（評価対象）：
              {pm.matched_products.map((p) => p.name).join("、")}
            </Badge>
            <ul className="mt-3 space-y-1">
              {pm.matched_products.map((p) => (
                <li key={p.name} className="text-sm text-text">
                  <span className="font-medium text-ink">{p.name}</span>
                  <span className="text-muted">
                    {" "}
                    （ヒット語:{" "}
                    <code className="rounded bg-surface-2 px-1 font-mono text-xs">
                      {p.matched_via}
                    </code>
                    ）
                  </span>
                  {p.notes && (
                    <span className="block text-xs text-muted">{p.notes}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <Badge tone="warn">自社品該当なし（評価対象外の可能性）</Badge>
        )}
      </Section>

      {/* ② 患者 */}
      <Section num="②" title="患者">
        <div className="flex gap-8">
          <div>
            <div className="font-mono text-xs uppercase tracking-wider text-muted">
              年齢
            </div>
            <div className="mt-1 text-lg font-bold text-ink">
              {dash(ext.patient.age)}
            </div>
          </div>
          <div>
            <div className="font-mono text-xs uppercase tracking-wider text-muted">
              性別
            </div>
            <div className="mt-1 text-lg font-bold text-ink">
              {dash(ext.patient.sex)}
            </div>
          </div>
        </div>
      </Section>

      {/* ③ 有害事象 + MedDRA */}
      <Section num="③" title="有害事象 ＋ MedDRAコード提案">
        <Table
          head={[
            "事象",
            "MedDRA PT",
            "PTコード",
            "コード由来",
            "出典",
            "発現日",
            "転帰",
            "報告重篤度",
          ]}
        >
          {ext.adverse_events.map((ae, i) => {
            const m = meddra[i];
            return (
              <tr key={`${ae.term}-${i}`}>
                <td className={`${TD} font-medium text-ink`}>{ae.term}</td>
                <td className={TD}>{dash(m?.pt_name_ja)}</td>
                <td className={`${TD} font-mono text-xs`}>{dash(m?.pt_code)}</td>
                <td className={`${TD} text-xs text-muted`}>{dash(m?.coded_by)}</td>
                <td className={`${TD} text-xs`}>
                  {SOURCE_LABELS[ae.source] ?? ae.source}
                </td>
                <td className={`${TD} whitespace-nowrap`}>{dash(ae.onset_date)}</td>
                <td className={TD}>{dash(ae.outcome)}</td>
                <td className={TD}>{dash(ae.seriousness_reported)}</td>
              </tr>
            );
          })}
        </Table>
      </Section>

      {/* ④ 重篤度 */}
      <Section
        num="④"
        title="重篤度（報告 vs 企業評価 / ICH E2A）"
        caption="🔴 重篤 は基準1つ以上に該当、🟡 要確認 は疑いのみ（安全側でHITL）。「⚠️ 差異」は報告上の重篤度と企業評価がずれた事象（過小報告を防ぐ着目点）。"
      >
        {data.seriousness.length === 0 ? (
          <p className="text-sm text-muted">—</p>
        ) : (
          <Table head={["事象", "報告重篤度", "企業評価", "差異", "該当基準", "根拠"]}>
            {data.seriousness.map((s, i) => {
              const rep = reportedIsSerious(s.reported);
              const diff = rep !== null && rep !== s.is_serious;
              const ev =
                s.hits.find((h) => h.evidence_quote)?.evidence_quote ??
                s.rationale;
              return (
                <tr key={`${s.term}-${i}`}>
                  <td className={`${TD} font-medium text-ink`}>{s.term}</td>
                  <td className={TD}>{dash(s.reported)}</td>
                  <td className={TD}>
                    <Badge tone={verdictTone("seriousness", s.verdict)}>
                      {s.verdict}
                    </Badge>
                  </td>
                  <td className={TD}>
                    {diff ? <Badge tone="warn">⚠️ 差異</Badge> : ""}
                  </td>
                  <td className={`${TD} text-xs`}>
                    {s.hits.map((h) => h.criterion).join("、") || "—"}
                  </td>
                  <td className={`${TD} text-xs text-muted`}>{dash(ev)}</td>
                </tr>
              );
            })}
          </Table>
        )}
      </Section>

      {/* ⑤ 既知/未知 */}
      <Section
        num="⑤"
        title="既知/未知（添付文書との照合）"
        caption={
          data.expectedness.length > 0
            ? "🟡 要確認 は一致が確実でないもの。安全側で未知として扱い、根拠を添えてHITLに回します（過度に既知と読み込んで報告漏れを招かないため）。"
            : undefined
        }
      >
        {data.expectedness.length === 0 ? (
          <p className="text-sm text-muted">
            該当する添付文書がないため、既知/未知は判定していません。
          </p>
        ) : (
          <div className="space-y-4">
            {data.expectedness.map((drug) => (
              <div key={drug.drug_name}>
                <p className="mb-2 text-sm text-text">
                  <span className="font-medium text-ink">{drug.drug_name}</span>
                  <span className="text-muted">
                    {" "}
                    （添付文書:{" "}
                    <code className="rounded bg-surface-2 px-1 font-mono text-xs">
                      {drug.label_document}
                    </code>
                    ）
                  </span>
                </p>
                <Table head={["事象", "判定", "一致", "該当箇所", "根拠（添付文書の記載）"]}>
                  {drug.assessments.map((a, i) => (
                    <tr key={`${a.term}-${i}`}>
                      <td className={`${TD} font-medium text-ink`}>{a.term}</td>
                      <td className={TD}>
                        <Badge tone={verdictTone("expectedness", a.verdict)}>
                          {a.verdict}
                        </Badge>
                      </td>
                      <td className={`${TD} text-xs`}>{dash(a.match_type)}</td>
                      <td className={`${TD} text-xs`}>
                        {dash(a.evidence_section)}
                      </td>
                      <td className={`${TD} text-xs text-muted`}>
                        {dash(a.evidence_quote ?? a.rationale)}
                      </td>
                    </tr>
                  ))}
                </Table>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ⑥ 因果関係 */}
      <Section
        num="⑥"
        title="因果関係（時間的・保守的評価）"
        caption="トリアージの保守的評価：本剤投与後に発現＝🔴 否定できない（スコープ維持）。投与開始前、または中止後で明らかに時間的に不整合な時のみ 🟢 否定できる。"
      >
        {data.causality.length === 0 ? (
          <p className="text-sm text-muted">—</p>
        ) : (
          <Table head={["事象", "因果関係", "発現時期", "根拠"]}>
            {data.causality.map((c, i) => (
              <tr key={`${c.term}-${i}`}>
                <td className={`${TD} font-medium text-ink`}>{c.term}</td>
                <td className={TD}>
                  <Badge tone={verdictTone("causality", c.verdict)}>
                    {c.verdict}
                  </Badge>
                </td>
                <td className={`${TD} text-xs`}>{dash(c.onset_relation)}</td>
                <td className={`${TD} text-xs text-muted`}>
                  {dash(c.evidence_quote ?? c.rationale)}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* ⑦ 過去症例の判例 */}
      <Section
        num="⑦"
        title="過去症例の判例（一貫性）"
        caption={
          data.precedent.some((p) => p.n_cases)
            ? "過去に承認された症例で同じMedDRA PTがどう判定されたか（参考情報・自動では判定を変えません）。⚠️ は今回のドラフトと過去の多数派が不一致で、レビュー要注意です。"
            : undefined
        }
      >
        {!data.precedent.some((p) => p.n_cases) ? (
          <p className="text-sm text-muted">
            同一MedDRA PTの過去承認症例は見つかりませんでした。
          </p>
        ) : (
          <Table
            head={[
              "事象",
              "過去件数",
              "重篤度(過去)",
              "因果(過去)",
              "既知/未知(過去)",
              "不一致",
              "参照症例",
            ]}
          >
            {data.precedent
              .filter((p) => p.n_cases)
              .map((p, i) => {
                const conflictAxes = (p.conflicts ?? [])
                  .map((a) => AXIS_LABELS[a] ?? a)
                  .join("・");
                return (
                  <tr key={`${p.term}-${i}`}>
                    <td className={`${TD} font-medium text-ink`}>{p.term}</td>
                    <td className={`${TD} tabular-nums`}>{p.n_cases}</td>
                    <td className={`${TD} text-xs`}>{counts(p.seriousness)}</td>
                    <td className={`${TD} text-xs`}>{counts(p.causality)}</td>
                    <td className={`${TD} text-xs`}>{counts(p.expectedness)}</td>
                    <td className={TD}>
                      {conflictAxes ? (
                        <Badge tone="warn">⚠️ {conflictAxes}</Badge>
                      ) : (
                        ""
                      )}
                    </td>
                    <td className={`${TD} text-xs text-muted`}>
                      {(p.case_ids ?? []).join("、") || "—"}
                    </td>
                  </tr>
                );
              })}
          </Table>
        )}
      </Section>

      {/* 過去データの反映 / 参考 (influence) */}
      <Section
        num={data.influence_mode === "applied" ? "🟢" : "⚪"}
        title={
          data.influence_mode === "applied"
            ? "過去データの反映（モード: 反映）"
            : "過去データ（参考・判定は今回の症例のみ）"
        }
      >
        {data.influence_mode === "applied" ? (
          data.influence.some((i) => i.applied) ? (
            <Table head={["事象", "軸", "由来", "変更", "内容"]}>
              {data.influence
                .filter((i) => i.applied)
                .map((it, i) => (
                  <tr key={`${it.term}-${i}`}>
                    <td className={`${TD} font-medium text-ink`}>{it.term}</td>
                    <td className={`${TD} text-xs`}>
                      {AXIS_LABELS[it.axis] ?? it.axis}
                    </td>
                    <td className={`${TD} text-xs`}>
                      {INFLUENCE_SOURCE_LABELS[it.source] ?? it.source}
                    </td>
                    <td className={`${TD} whitespace-nowrap text-xs`}>
                      {it.from_verdict}→{it.to_verdict}
                    </td>
                    <td className={`${TD} text-xs text-muted`}>{it.note}</td>
                  </tr>
                ))}
            </Table>
          ) : (
            <p className="text-sm text-muted">
              今回、過去データによる調整はありませんでした。
            </p>
          )
        ) : data.influence.length > 0 ? (
          <Table head={["事象", "軸", "由来", "メモ"]}>
            {data.influence.map((it, i) => (
              <tr key={`${it.term}-${i}`}>
                <td className={`${TD} font-medium text-ink`}>{it.term}</td>
                <td className={`${TD} text-xs`}>
                  {AXIS_LABELS[it.axis] ?? it.axis}
                </td>
                <td className={`${TD} text-xs`}>
                  {INFLUENCE_SOURCE_LABELS[it.source] ?? it.source}
                </td>
                <td className={`${TD} text-xs text-muted`}>{it.note}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <p className="text-sm text-muted">
            参考にできる過去データはありませんでした。
          </p>
        )}
      </Section>

      {/* 読み取ったテキスト（出典） */}
      <details className="rounded-xl border border-border bg-surface p-5 shadow-sm">
        <summary className="cursor-pointer text-sm font-bold text-ink">
          読み取ったテキスト（出典）
        </summary>
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs leading-relaxed text-text">
          {data.source_text}
        </pre>
      </details>
    </div>
  );
}
