import type { ReviewOutcome, TriageContent } from "@/lib/types";

// Every reason a verdict differs from what the model first produced, in one
// shape. Two sources feed it:
//
//   - influence: past data folded into the draft before review (the IME list, or
//     precedent from past approved cases). InfluenceItem already carries
//     from_verdict -> to_verdict, so the pre-influence verdict is recoverable
//     from a SINGLE run. That matters: re-running the case to get a "before"
//     would mix in LLM run-to-run variation and stop isolating the effect — the
//     same reasoning the evaluation harness uses.
//   - overrides: what the human reviewer changed at the approval gate.

export type ChangeSource = "reviewer" | "IME" | "precedent";

export type VerdictChange = {
  axis: string;
  term: string;
  drug: string | null;
  from: string;
  to: string;
  source: ChangeSource;
  reason: string | null;
};

export const SOURCE_LABEL: Record<ChangeSource, string> = {
  reviewer: "人手レビュー",
  IME: "以前のFB(IME)",
  precedent: "過去症例",
};

export const changeKey = (axis: string, term: string, drug?: string | null) =>
  `${axis}::${term}::${drug ?? ""}`;

export function buildChanges(
  data: TriageContent,
  review?: ReviewOutcome | null,
): VerdictChange[] {
  const out: VerdictChange[] = [];

  for (const it of data.influence) {
    if (!it.applied || !it.from_verdict || !it.to_verdict) continue;
    out.push({
      axis: it.axis,
      term: it.term,
      drug: it.drug_name,
      from: it.from_verdict,
      to: it.to_verdict,
      source: it.source === "IME" ? "IME" : "precedent",
      reason: it.note,
    });
  }

  // Applied after the influence layer, so a reviewer override is the final word.
  for (const o of review?.overrides ?? []) {
    out.push({
      axis: o.axis,
      term: o.term,
      drug: o.drug_name,
      from: o.original_verdict,
      to: o.new_verdict,
      source: "reviewer",
      reason: o.rationale,
    });
  }

  return out;
}

/** Latest change per (axis, term, drug) — reviewer wins over influence. */
export function indexChanges(changes: VerdictChange[]): Map<string, VerdictChange> {
  const m = new Map<string, VerdictChange>();
  for (const c of changes) m.set(changeKey(c.axis, c.term, c.drug), c);
  return m;
}
