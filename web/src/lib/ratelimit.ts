// Fixed-window per-IP rate limiting for the expensive BFF routes.
//
// In-memory on purpose: this guards a portfolio demo, not a multi-tenant API.
// The trade-off is explicit — App Runner may run more than one instance, and
// each keeps its own counters, so the effective limit is (limit x instances).
// At demo scale that is fine; a shared store (Redis/DynamoDB) is the upgrade
// path if this ever needs to be exact.

type Bucket = { count: number; resetAt: number };

const buckets = new Map<string, Bucket>();

/** Drop expired buckets so the map cannot grow without bound. */
function sweep(now: number) {
  if (buckets.size < 1000) return;
  for (const [key, b] of buckets) if (b.resetAt <= now) buckets.delete(key);
}

export type RateLimitResult = {
  ok: boolean;
  remaining: number;
  retryAfterSec: number;
};

/**
 * Count one hit for `key`. Returns ok=false once `limit` is exceeded inside
 * the current `windowSec` window.
 */
export function hit(key: string, limit: number, windowSec: number): RateLimitResult {
  const now = Date.now();
  sweep(now);

  const b = buckets.get(key);
  if (!b || b.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + windowSec * 1000 });
    return { ok: true, remaining: limit - 1, retryAfterSec: windowSec };
  }

  b.count += 1;
  const retryAfterSec = Math.max(1, Math.ceil((b.resetAt - now) / 1000));
  return { ok: b.count <= limit, remaining: Math.max(0, limit - b.count), retryAfterSec };
}

/**
 * Best-effort client identity. Behind App Runner the real address is the first
 * entry of x-forwarded-for; everything else is a fallback so local dev still
 * partitions sensibly.
 */
export function clientKey(request: Request): string {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0]!.trim();
  return request.headers.get("x-real-ip") ?? "local";
}

/** 429 with the standard Retry-After header, in the API's {detail} shape. */
export function tooManyRequests(retryAfterSec: number): Response {
  return Response.json(
    {
      detail:
        `混み合っています。デモのため実行回数を制限しています（あと約 ${retryAfterSec} 秒お待ちください）。`,
    },
    { status: 429, headers: { "retry-after": String(retryAfterSec) } },
  );
}

// ---- global (not per-IP) daily cap ----
//
// The per-IP limit bounds what ONE visitor can spend; it does nothing about many
// visitors, or one visitor on many addresses. This cap bounds the TOTAL number of
// paid runs per day, which is what actually protects the bill.
//
// Also in-memory, so it is exact only while the service runs a single instance —
// which is why the App Runner service is deployed with maxSize=1. Treat it as
// defense in depth behind a hard spending cap set at the LLM provider.

let dayKey = "";
let dayCount = 0;

/** UTC date, so the window does not shift with the viewer's timezone. */
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function hitGlobalDaily(limit: number): { ok: boolean; used: number } {
  const d = today();
  if (d !== dayKey) {
    dayKey = d;
    dayCount = 0;
  }
  dayCount += 1;
  return { ok: dayCount <= limit, used: dayCount };
}

export function dailyCapReached(): Response {
  return Response.json(
    {
      detail:
        "本日のデモ実行上限に達しました。日付が変わると再度お試しいただけます（費用管理のため上限を設けています）。",
    },
    { status: 429 },
  );
}
