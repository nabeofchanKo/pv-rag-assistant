import { proxyToBackend } from "@/lib/backend";

// BFF proxy for the RAG query. Browser → this handler → FastAPI POST /query.
// POST route handlers are dynamic (never cached), which is what we want.
export async function POST(request: Request) {
  return proxyToBackend("/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
  });
}
