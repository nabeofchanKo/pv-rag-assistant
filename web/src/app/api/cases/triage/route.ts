import { proxyToBackend } from "@/lib/backend";
import {
  DEMO_MODE,
  GLOBAL_DAILY_TRIAGE,
  LIMITS,
  isAllowedSample,
  readSample,
  uploadsDisabled,
} from "@/lib/demo";
import {
  clientKey,
  dailyCapReached,
  hit,
  hitGlobalDaily,
  tooManyRequests,
} from "@/lib/ratelimit";

// BFF proxy for starting a triage run. Browser → this handler → FastAPI
// POST /cases/triage.
//
// Two input shapes:
//   { "sample": "case_001.txt" }  — always allowed; the BFF reads the bundled
//                                   file itself, so no caller content is trusted.
//   multipart/form-data           — a real upload; refused while DEMO_MODE is on.
//
// Triage is the expensive route (~20s, several LLM calls), so it carries the
// tightest per-IP limit.
export async function POST(request: Request) {
  const rl = hit(`triage:${clientKey(request)}`, LIMITS.triage.limit, LIMITS.triage.windowSec);
  if (!rl.ok) return tooManyRequests(rl.retryAfterSec);

  // Bounds total paid runs per day, which the per-IP limit alone does not.
  if (!hitGlobalDaily(GLOBAL_DAILY_TRIAGE).ok) return dailyCapReached();

  const qs = new URL(request.url).search;
  const contentType = request.headers.get("content-type") ?? "";

  let form: FormData;
  if (contentType.includes("application/json")) {
    const body = (await request.json().catch(() => null)) as { sample?: unknown } | null;
    if (!isAllowedSample(body?.sample)) {
      return Response.json(
        { detail: "指定されたサンプル症例は利用できません。" },
        { status: 400 },
      );
    }
    form = new FormData();
    form.append("file", await readSample(body.sample));
  } else {
    if (DEMO_MODE) return uploadsDisabled();
    form = await request.formData();
  }

  return proxyToBackend(`/cases/triage${qs}`, { method: "POST", body: form });
}
