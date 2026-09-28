import { defineConfig, devices } from "@playwright/test";

// E2E smoke suite. Two servers are started for the run:
//   1. e2e/fake-backend.mjs — replays JSON recorded from the real FastAPI app
//   2. the Next.js app, with BACKEND_URL pointed at (1)
// so the browser, the page code AND the BFF route handlers all run for real,
// while the run stays free (no LLM calls) and deterministic.
//
// Ports are deliberately not the dev defaults (3000/8000): a developer's own
// `npm run dev` or real backend must never be picked up by accident, which is
// also why reuseExistingServer is off.

const WEB_PORT = 3100;
const FAKE_PORT = 8765;

export default defineConfig({
  testDir: "./e2e",
  // The fake backend remembers the last approve body — keep runs serial so two
  // tests never read each other's request.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    // Pin the browser language: the proxy redirects locale-less paths by it.
    locale: "ja-JP",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/fake-backend.mjs",
      url: `http://127.0.0.1:${FAKE_PORT}/`,
      env: { FAKE_BACKEND_PORT: String(FAKE_PORT) },
      reuseExistingServer: false,
    },
    {
      command: `npx next dev --port ${WEB_PORT} --hostname 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}/`,
      env: {
        BACKEND_URL: `http://127.0.0.1:${FAKE_PORT}`,
        // Same policy as production: samples only, uploads refused.
        DEMO_MODE: "1",
        // The limiter is real code under test elsewhere; here it would only
        // make the suite flaky once it runs more than 5 triages in 10 minutes.
        RATE_LIMIT_TRIAGE: "1000",
        GLOBAL_DAILY_TRIAGE: "1000",
      },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
