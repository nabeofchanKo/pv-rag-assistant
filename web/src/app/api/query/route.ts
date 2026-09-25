import { proxyToBackend } from "@/lib/backend";
import { LIMITS } from "@/lib/demo";
import { clientKey, hit, tooManyRequests } from "@/lib/ratelimit";

// BFF proxy for the RAG query. Browser → this handler → FastAPI POST /query.
// POST route handlers are dynamic (never cached), which is what we want.
export async function POST(request: Request) {
  const rl = hit(`query:${clientKey(request)}`, LIMITS.query.limit, LIMITS.query.windowSec);
  if (!rl.ok) return tooManyRequests(rl.retryAfterSec);

  return proxyToBackend("/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
  });
}
