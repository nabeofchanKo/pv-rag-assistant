# 0001 — Expectedness (既知/未知) via per-AE RAG over the drug label

- **Status:** Accepted
- **Date:** 2026-08-22
- **Phase:** 3 (evaluation tasks), slice 3a

## Context

Expectedness asks: is a reported adverse event already described in the suspect
drug's package insert (添付文書)? It is the first Phase 3 evaluation task and the
first feature that turns the project's dormant RAG stack (chunk → embed → store →
retrieve) toward *evaluation* rather than Q&A.

## Options considered

- **A — Per-AE RAG retrieval + LLM judgment.** Chunk & embed the insert; for each
  adverse event retrieve the most relevant 副作用/相互作用 passages of that drug's
  label and have an LLM judge listed/not-listed, grounded in the retrieved text.
- **B — Structured ADR list (authored YAML) + deterministic match.** Curate the
  known ADRs per drug up front and match like the product master. Reliable and
  auditable, but not "RAG" and does not showcase document understanding.
- **C — Hybrid: read the label once into a structured, cited ADR list, cache it,
  then match each AE against that list.** Best of both, but the most work.

## Decision

Adopt **Approach A** now. It reuses the existing retrieval infrastructure, scales
to real multi-page inserts, keeps every judgment grounded in a cited passage, and
is the most representative of the project's RAG thesis. Interaction-section
mentions (e.g. warfarin → INR上昇/出血) count as 既知 — the natural triage call.

**Approach C is recorded for a later A/B** comparison against A (see the README
"Design note / 設計メモ"); it is also the shape the future MedDRA-PT comparison
can plug into.

## Consequences

- (+) Reuses `RetrieverService` (a separate `drug_labels` Chroma collection,
  metadata-scoped to one drug) and the chunker; grounded, citable output.
- (+) Extraction stays faithful ("transcribes, never judges"); judgment lives in a
  separate `ExpectednessService`, so the two concerns don't bleed.
- (−) Non-deterministic. Mitigated by grounding every verdict in evidence and
  defaulting to the safe side when nothing supports 既知.
- The confidence handling that this safe-side default grew into is [ADR 0002](0002-expectedness-confidence-gate.md).
