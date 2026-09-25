import { proxyToBackend } from "@/lib/backend";
import { DEMO_MODE, LIMITS, isAllowedSample, readSample, uploadsDisabled } from "@/lib/demo";
import { clientKey, hit, tooManyRequests } from "@/lib/ratelimit";

// BFF proxy for document upload. Browser → this handler → FastAPI
// POST /documents/upload.
//
// Same two input shapes as the triage route:
//   { "sample": "case_001.txt" }  — always allowed; the BFF reads the bundled
//                                   file itself, so the demo can still populate
//                                   the RAG index without accepting user content.
//   multipart/form-data           — a real upload; refused while DEMO_MODE is on.
export async function POST(request: Request) {
  const rl = hit(`query:${clientKey(request)}`, LIMITS.query.limit, LIMITS.query.windowSec);
  if (!rl.ok) return tooManyRequests(rl.retryAfterSec);

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
    // Re-post the multipart FormData as-is; fetch sets the multipart
    // boundary/content-type, so we must NOT set it by hand.
    form = await request.formData();
  }

  return proxyToBackend("/documents/upload", { method: "POST", body: form });
}
