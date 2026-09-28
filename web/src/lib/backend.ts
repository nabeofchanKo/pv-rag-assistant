// Server-side only. The FastAPI backend base URL.
//
// In the Backend-for-Frontend pattern the browser never calls FastAPI directly:
// the route handlers under src/app/api/* proxy to it server-to-server. That means
// no CORS, the API key/URL stay off the client, and FastAPI can remain private.
// This module must only be imported from route handlers / server components.

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Shared secret proving a request came from this BFF. On App Runner both
// services get public URLs, so without it the API would be directly callable,
// giving back the isolation the BFF has locally (where the API is only on the
// compose network). Unset locally = header omitted, and the API does not require it.
const INTERNAL_TOKEN = process.env.INTERNAL_API_TOKEN;

/**
 * Proxy a request to the FastAPI backend and pass its JSON + status straight
 * through. Network failures (backend down) are normalized to a 502 with a
 * `detail` message so the client always receives the same `{ detail }` shape.
 */
export async function proxyToBackend(
  path: string,
  init: RequestInit,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (INTERNAL_TOKEN) headers.set("x-internal-token", INTERNAL_TOKEN);

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });
  } catch {
    return Response.json(
      { detail: `バックエンドに接続できません (${BACKEND_URL})。起動しているか確認してください。` },
      { status: 502 },
    );
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
