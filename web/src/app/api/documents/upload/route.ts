import { proxyToBackend } from "@/lib/backend";

// BFF proxy for document upload. Browser → this handler → FastAPI
// POST /documents/upload. We re-post the multipart FormData as-is; fetch sets
// the multipart boundary/content-type, so we must NOT set it by hand.
export async function POST(request: Request) {
  const form = await request.formData();
  return proxyToBackend("/documents/upload", {
    method: "POST",
    body: form,
  });
}
