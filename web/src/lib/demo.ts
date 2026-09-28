// Demo-mode policy. Server-only — imported by route handlers, never the client.
//
// The public demo must not become an open door to paid LLM calls, so input is
// restricted to the bundled sample cases. Crucially the restriction is enforced
// HERE, not by hiding the file picker: the client sends a sample *name*, and the
// BFF reads that file from disk itself. No caller-supplied file content is
// forwarded to the backend while demo mode is on.

import { readFile } from "node:fs/promises";
import path from "node:path";
import { SAMPLE_META } from "./samples-meta";

/** Demo mode is ON unless explicitly disabled — fail closed. */
export const DEMO_MODE = process.env.DEMO_MODE !== "0";

/** The only cases the demo will run — derived from the sample catalogue, so the
 * allowlist and the documented cases cannot drift apart. */
export const SAMPLES = SAMPLE_META.map((s) => ({
  file: s.file,
  label: s.label,
  hint: s.hint,
}));

const ALLOWED = new Set(SAMPLE_META.map((s) => s.file));

export function isAllowedSample(name: unknown): name is string {
  return typeof name === "string" && ALLOWED.has(name);
}

/**
 * Read a bundled sample as a File, ready to forward as multipart.
 * `public/` sits next to the server bundle in the standalone image, so
 * process.cwd() resolves in both dev and container.
 */
export async function readSample(name: string): Promise<File> {
  if (!isAllowedSample(name)) throw new Error(`not an allowed sample: ${name}`);
  const full = path.join(process.cwd(), "public", "samples", name);
  const buf = await readFile(full);
  return new File([new Uint8Array(buf)], name, { type: "text/plain" });
}

/** Refusal used when demo mode blocks a caller-supplied upload. */
export function uploadsDisabled(): Response {
  return Response.json(
    {
      detail:
        "このデモではファイルのアップロードを受け付けていません。同梱のサンプル症例からお試しください。",
    },
    { status: 403 },
  );
}

// Per-IP limits for the expensive routes. A triage run is ~20s and several LLM
// calls, so it is much tighter than a RAG query.
export const GLOBAL_DAILY_TRIAGE = Number(process.env.GLOBAL_DAILY_TRIAGE ?? 40);

export const LIMITS = {
  triage: { limit: Number(process.env.RATE_LIMIT_TRIAGE ?? 5), windowSec: 600 },
  query: { limit: Number(process.env.RATE_LIMIT_QUERY ?? 20), windowSec: 600 },
  approve: { limit: Number(process.env.RATE_LIMIT_APPROVE ?? 30), windowSec: 600 },
};
