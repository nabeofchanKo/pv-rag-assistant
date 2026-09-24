# 0013 — Replace the Streamlit frontend with Next.js behind a BFF

- **Status:** Accepted
- **Date:** 2026-09-25
- **Phase:** 6 (frontend & deployment)
- **Evidence:** live end-to-end verification through the running app (RAG Q&A, triage draft, out-of-scope branch, HITL approve/reject with audit trail) + `next build` type-check across the app

## Context

Phases 0–5 built the whole product behind a **FastAPI REST API**, with Streamlit
(`frontend/app.py`, 608 lines) consuming it over HTTP. That split is the reason
Phase 6 is a *frontend swap, not new development*: the API contract
(`/documents/upload`, `/query`, `/cases/triage` → draft + `thread_id` →
`/cases/{thread_id}/approve`) already exists and Streamlit was already just an
HTTP client. **No backend change is required, and none was made.**

Two goals drove the swap. First, the product goal: a triage assistant that a
drug-safety reviewer actually operates needs a real UI (per-event tables,
disclosure of evidence, an editable review form), which Streamlit's
`data_editor` makes awkward. Second, the portfolio goal: a **deployed, clickable
product** is the competency being demonstrated, and Streamlit reads as a
prototype.

The new constraint the swap introduces is that the browser and the API are now
separate origins, which forces a choice about how the browser reaches FastAPI.

## Options

1. **Keep Streamlit and deploy it.** Zero frontend work. But it stays
   prototype-shaped, and the reviewer UX (per-event disclosure, inline edit)
   stays awkward. Rejected on both goals.
2. **Next.js as a pure client (SPA) calling FastAPI directly.** Simplest mental
   model. But it requires **CORS** on the backend (a backend change), exposes the
   FastAPI origin publicly, and any credential the frontend needs would live in
   the browser bundle.
3. **Next.js with a Backend-for-Frontend (BFF).** The browser talks only to the
   Next.js server; route handlers under `src/app/api/*` proxy server-to-server to
   FastAPI. Adds one hop and a thin proxy layer per endpoint.

## Decision

Adopt **option 3**: Next.js 16 (App Router, TypeScript, Tailwind v4) in `web/`,
consuming the existing API through a BFF. `frontend/app.py` (Streamlit) is
removed now that the Next.js UI reaches feature parity.

- **BFF proxy.** `web/src/lib/backend.ts` holds `BACKEND_URL` (server-only) and a
  `proxyToBackend()` helper that passes the upstream status/body through and
  normalizes a dead backend to a 502 with the same `{ detail }` shape the API
  uses. Route handlers: `api/query`, `api/documents/upload`,
  `api/cases/triage`, `api/cases/[thread_id]/approve`. POST handlers are dynamic
  by default, which is what a proxy wants.
- **Typed contract, hand-written.** `web/src/lib/types.ts` mirrors
  `backend/app/schemas.py` (including Pydantic `computed_field`s, which *are*
  serialized: `is_serious`, `is_expected`, `is_excludable`,
  `is_company_product_present`). Hand-written rather than generated: the contract
  is small and stable, and a codegen step would buy little at this size. The
  drift risk this creates is real and is answered by a planned contract test
  (TS types vs `/openapi.json`), not by hope.
- **Verdict option lists mirror the backend.** `SER/CAU/EXP_OPTIONS` in
  `web/src/lib/labels.ts` restate `ALLOWED_VERDICTS`
  (`services/triage_graph.py`); a value outside them is rejected 422 server-side,
  so the UI constrains but the backend still enforces.
- **Deploy target (decided, executed in Step 5):** **AWS App Runner** for the
  FastAPI container (via ECR) + hosting for the Next.js app, chosen over a
  single box (Lightsail/EC2 + compose), ECS Fargate + ALB, and Vercel. Rationale:
  both ends managed, git-push CI/CD, no VPC/task-definition work, ~$10–30/mo —
  the balance point for a portfolio demo, with a stated upgrade path (Fargate +
  ALB, checkpointer on RDS/Postgres) rather than a built one.

## Consequences

- (+) **No CORS, and the backend can stay private.** The browser only ever sees
  the Next.js origin. Any API credential stays server-side. This is the main
  reason to pay for the extra hop.
- (+) **Backend untouched — 0 lines.** The whole of Phases 0–5 (LangGraph triage,
  the safety invariants, provider switching) is unchanged, so nothing validated
  in earlier phases is put at risk by the UI work.
- (+) **The BFF is the natural control point** for the demo protections Step 5
  needs (sample-only input enforcement, rate limiting) — they belong server-side,
  not in the client where they could be bypassed.
- (−) **One more hop and a proxy file per endpoint.** Cheap here (four routes),
  but it is boilerplate that grows with the API surface.
- (−) **Two languages, one contract.** The TS types can drift from the Pydantic
  schemas silently. Accepted deliberately, with a contract test planned as the
  mitigation.
- (−) **The local/hybrid generation tiers do not deploy.** Ollama needs a GPU
  host, so the cloud demo runs the **OpenAI tier**; the local and hybrid tiers
  (ADR 0011, 0012) remain a validated, documented flag flip rather than something
  the public demo exercises.
- **State in the cloud:** reference indexes rebuild at startup
  (`ensure_indexed()` is idempotent, so no persistent disk is required), while
  mutable state (HITL thread checkpoints, precedent, IME promotions) is
  **ephemeral for the demo**, with the upgrade path (LangGraph Postgres
  checkpointer + RDS) documented rather than built.
- **Testing note learned the hard way:** approving a case in the real app mutates
  tracked reference data — an IME promotion appends to
  `data/reference/ime_pt.csv` (which would make every future event with that PT
  fire E2A criterion 6) and an approval writes precedent to
  `backend/past_cases/`. `ImeReference` and `PrecedentService` are in-memory
  `@lru_cache` singletons, so reverting the file is not enough; the backend must
  be restarted. HITL testing should use a temporary IME path, as Phase 4c did.
