import { proxyToBackend } from "@/lib/backend";
import { LIMITS } from "@/lib/demo";
import { clientKey, hit, tooManyRequests } from "@/lib/ratelimit";

// BFF proxy for the HITL decision. Browser → this handler → FastAPI
// POST /cases/{thread_id}/approve. Backend validation errors (422 unknown axis /
// bad verdict, 409 already finalized, 404 unknown thread) pass straight through.
export async function POST(
  request: Request,
  ctx: RouteContext<"/api/cases/[thread_id]/approve">,
) {
  const rl = hit(`approve:${clientKey(request)}`, LIMITS.approve.limit, LIMITS.approve.windowSec);
  if (!rl.ok) return tooManyRequests(rl.retryAfterSec);

  const { thread_id } = await ctx.params;
  return proxyToBackend(`/cases/${encodeURIComponent(thread_id)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
  });
}
