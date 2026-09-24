import { proxyToBackend } from "@/lib/backend";

// BFF proxy for starting a triage run. Browser → this handler → FastAPI
// POST /cases/triage. The multipart FormData (the case file) is forwarded as-is,
// and any query string (e.g. ?influence=advisory, ?auto_approve=true) is passed
// through to the backend.
export async function POST(request: Request) {
  const form = await request.formData();
  const qs = new URL(request.url).search;
  return proxyToBackend(`/cases/triage${qs}`, {
    method: "POST",
    body: form,
  });
}
