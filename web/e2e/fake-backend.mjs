// A stand-in for the FastAPI backend, for the E2E suite only.
//
// The BFF is pointed here (BACKEND_URL) instead of at FastAPI, so a test run
// exercises browser → Next.js route handler → HTTP → "backend" for real, but
// costs nothing and returns the same bytes every time. The bytes are recorded
// from the real backend by record_fixtures.py — the fake never invents a shape.
//
// It also remembers the last approve body it received (GET /__last-approve),
// so a test can check what the BFF actually forwarded, not just what the page
// rendered afterwards.
//
// Deliberately dependency-free (node:http only).

import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const PORT = Number(process.env.FAKE_BACKEND_PORT ?? 8765);
const fixture = (name) =>
  readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf-8");

// Which recorded response each sample produces.
const TRIAGE = {
  "case_001.txt": "case_001.draft.json",
  "case_004.txt": "case_004.out_of_scope.json",
};

let lastApprove = null;

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks).toString("utf-8");
}

createServer(async (req, res) => {
  const url = new URL(req.url, "http://fake");

  if (req.method === "GET" && url.pathname === "/") return send(res, 200, { ok: true });

  if (req.method === "POST" && url.pathname === "/cases/triage") {
    // The BFF forwards multipart; the sample's filename is all we need to pick
    // a fixture, so match it out of the Content-Disposition header.
    const body = await readBody(req);
    const name = body.match(/filename="([^"]+)"/)?.[1];
    const file = name && TRIAGE[name];
    if (!file) return send(res, 422, { detail: `fake backend: no fixture for ${name}` });
    return send(res, 200, fixture(file));
  }

  const approve = url.pathname.match(/^\/cases\/([^/]+)\/approve$/);
  if (req.method === "POST" && approve) {
    lastApprove = { thread_id: decodeURIComponent(approve[1]), body: JSON.parse(await readBody(req)) };
    return send(res, 200, fixture("case_001.approved.json"));
  }

  if (req.method === "GET" && url.pathname === "/__last-approve") return send(res, 200, lastApprove);

  send(res, 404, { detail: `fake backend: ${req.method} ${url.pathname}` });
}).listen(PORT, "127.0.0.1", () => {
  console.log(`fake backend on http://127.0.0.1:${PORT}`);
});
