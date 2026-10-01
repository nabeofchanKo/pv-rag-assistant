# 0014 — MedDRA is not bundled: a fictional demo terminology + bring-your-own MedDRA

- **Status:** Accepted
- **Date:** 2026-10-01
- **Phase:** 6 (public portfolio hygiene)
- **Evidence:** retrieval bench re-run (hit rates identical) + tests ([backend/tests/test_meddra.py](../../backend/tests/test_meddra.py)); file layouts taken from the public *MedDRA Distribution File Format Document* and *MedDRA/J 配布ファイルフォーマット情報* (v27.0)

## Context

The repository is public and MIT-licensed. Until now it shipped
`data/meddra_sample/meddra_pt.csv`: 56 PTs with their **real MedDRA codes**,
**MedDRA/J Japanese names** and **Japanese SOC names**, and the same codes were
spread through the gold set, seed past cases, tests, E2E fixtures and an ADR. The
README called it "a small illustrative subset (MedDRA is licensed)" — which
admits the problem rather than solving it. MedDRA is owned by ICH and distributed
under subscription (MSSO; MedDRA/J by JMO). Being small does not make
redistributing it to non-subscribers acceptable, and the repo-wide MIT licence
made it look as if MedDRA content were being relicensed. Feedback from a reviewer
flagged it, and for a PV-background author it is an obvious interview question.

## Options

1. **Ask JMO/MSSO for permission.** The most certain outcome if granted, but slow
   and uncertain. Not waited on (the user's call).
2. **Fictional demo terminology only.** Replace codes and SOC names with
   self-made ones and state that this is not MedDRA. A small change, but a real
   licensee has no way to use the system.
3. **Option 2 + bring-your-own MedDRA.** Also read a licensed MedDRA/J ASCII
   distribution, selected by configuration, so the repo carries no MedDRA and a
   licensee plugs in their own.

## Decision

Adopt **option 3**.

- **Demo terminology** — `data/terminology/demo_pt.csv`. Codes are `DEMO-0001` …
  `DEMO-0056` (a format MedDRA cannot have; `DEMO-9001` is a test-only code that is
  not in the dictionary). SOC names are replaced by short self-made body-system
  labels (神経系, 消化器, 全身症状, …). Every
  code reference (gold, past cases, IME list, tests, E2E fixtures, ADR 0008) was
  remapped by one script, so the gold labels still point at the same concepts.
- **Term names are kept.** They are common clinical words (頭痛, 悪心, Headache …)
  and changing them would invalidate every retrieval and coding result. Some
  coincide with MedDRA/J's wording (浮動性めまい, 錯感覚, …). This is a known grey
  area, accepted for now and stated in the README rather than hidden.
- **Bring your own MedDRA** — `MEDDRA_PATH` may point at a folder instead of a
  CSV; `load_meddra_ascii` then reads `pt.asc` (code, English name), `pt_j.asc`
  (Japanese name), plus optional `mdhier.asc` (primary SOC) and `soc_j.asc`
  (Japanese SOC name). The documented layouts are followed: `$`-delimited, MSSO
  files end each line with a trailing `$` and JMO's `*_j.asc` do not, and the
  `*_j.asc` files are Shift-JIS. Fields are read by position, so the trailing `$`
  does not matter. A licensee's own IME list goes in `IME_PATH` the same way.
  `data/meddra/` is gitignored as the place to put licensed files.
- **The vector index follows the dictionary.** `ensure_indexed` used to skip
  whenever the collection was non-empty. After a dictionary swap that would keep
  stale codes, and the vector half of the hybrid retriever would silently return
  nothing. It now rebuilds when the stored codes differ from the dictionary's, and
  it adds documents in batches, since a full MedDRA has about 27k PTs.

## Consequences

- (+) The repository contains no MedDRA codes or SOC names, and says so plainly.
- (+) Retrieval is unchanged by construction: the names, the BM25 index and the
  embedded text are identical, and only the code strings differ. This was
  confirmed by re-running `experiments/scripts/embedding_retrieval_bench.py` after
  the remap. Every hit rate (hybrid / vector @1/3/5, all and hard subsets) matched
  the committed report for both OpenAI and bge-m3, and only the timings moved.
  That run also exercised the rebuild path, since the old on-disk indexes held the
  old codes. The SOC label shown to the coding LLM is the one input that changed.
  The LLM-backed triage eval was not re-run.
- (−) **One published number cannot be reproduced any more.** The single-LLM
  baseline's MedDRA 29% ([triage_baseline](../../experiments/triage_baseline.md))
  asked the model for real codes from memory and scored them against the gold's
  real codes. Against `DEMO-xxxx` it would score ~0% by construction. The figure
  is kept, labelled as measured before this change, in the README, the case
  study and EVALUATION.md. The pipeline's 100% is now stated with its scale
  (56 terms, against about 27k PTs in MedDRA).
- (+) A licensee can run the real dictionary without code changes, and the index
  rebuilds itself after the swap (covered by a test).
- (−) **Git history.** The removed files are still reachable in earlier commits on
  GitHub until the history is rewritten. That is a separate, destructive step
  (`git filter-repo` + force-push) and is tracked outside this ADR.
- (−) The ASCII loader is tested only on hand-made files in the documented layout,
  not on a real distribution (no licence here). Only PTs are loaded. LLT-level
  search, where real coding starts, is future work.
- (−) The demo has no LLT/HLT/HLGT hierarchy, so it cannot show hierarchy-aware
  behaviour. It is enough for what the project demonstrates (retrieval + selection
  + HITL).
