import { DEMO_MODE, SAMPLES } from "@/lib/demo";

// Public UI config. Lets the client render the right controls (sample buttons
// vs a file picker) without a second, separately-set NEXT_PUBLIC_ env var that
// could drift out of sync with the server-side enforcement in lib/demo.ts.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ demoMode: DEMO_MODE, samples: SAMPLES });
}
