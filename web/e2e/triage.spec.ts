import { expect, test, type Page } from "@playwright/test";
import approveRequest from "./fixtures/case_001.approve.request.json";
import draft from "./fixtures/case_001.draft.json";

// Smoke test of the reviewer's path through the triage page:
//   pick a sample → the draft renders → edit a verdict → approve → audit trail.
//
// The backend is e2e/fake-backend.mjs replaying recorded JSON (see
// playwright.config.ts). What that makes this suite good for: catching the UI or
// the BFF breaking. What it cannot catch: the backend changing its answers —
// that is the evaluation harness's job, and the contract test's for the shape.

const FAKE_BACKEND = "http://127.0.0.1:8765";

async function runSample(page: Page, label: string) {
  await page.goto("/triage");
  await page.getByRole("button", { name: new RegExp(label) }).click();
}

async function lastApprove(page: Page) {
  const res = await page.request.get(`${FAKE_BACKEND}/__last-approve`);
  return res.json();
}

test("a sample case renders as a draft awaiting review", async ({ page }) => {
  await runSample(page, "症例001");

  await expect(page.getByText("awaiting_review · レビュー待ち")).toBeVisible();
  await expect(page.getByText(draft.document_name)).toBeVisible();

  // Every block of the result view, top to bottom.
  await expect(page.getByRole("heading", { name: "判定サマリー" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "事象一覧" })).toBeVisible();
  for (const summary of ["患者・自社品の詳細", "過去データの扱い", "読み取ったテキスト（出典）"])
    await expect(page.locator("summary", { hasText: summary })).toBeVisible();
  await expect(page.getByRole("heading", { name: /レビュー・承認（HITL）/ })).toBeVisible();

  // One row per extracted adverse event, and nothing silently dropped.
  for (const ae of draft.extraction.adverse_events)
    await expect(page.locator("summary", { hasText: ae.term })).toBeVisible();
});

test("approving without a reviewer name is refused before anything is sent", async ({ page }) => {
  const before = await lastApprove(page);
  await runSample(page, "症例001");

  await page.getByRole("button", { name: "承認する" }).click();

  await expect(page.getByText("レビュー担当者名は必須です。")).toBeVisible();
  expect(await lastApprove(page)).toEqual(before);
});

test("an approval with an override reaches the backend and shows in the audit trail", async ({ page }) => {
  const ov = approveRequest.overrides[0];
  const original = draft.seriousness.find((s) => s.term === ov.term)!.verdict;
  await runSample(page, "症例001");

  // Replay exactly the decision that was recorded against the real backend.
  await page.getByPlaceholder("例：田中PV担当").fill(approveRequest.reviewer);
  await page.getByPlaceholder("所見があれば記入").fill(approveRequest.note);
  await page.getByLabel(`重篤度 ${ov.term} の変更後`).selectOption(ov.new_verdict);
  await page.getByLabel(`重篤度 ${ov.term} の変更理由`).fill(ov.rationale);
  await page.getByRole("button", { name: "承認する" }).click();

  // What the BFF forwarded is byte-for-byte the decision the real backend accepted.
  await expect(page.getByText(`✅ 承認済み — 担当: ${approveRequest.reviewer}`)).toBeVisible();
  const sent = await lastApprove(page);
  expect(sent.thread_id).toBe(draft.thread_id);
  expect(sent.body).toEqual(approveRequest);

  // The audit trail (section ⑧) keeps the original verdict next to the reviewer's.
  // Scoped because the same change also appears in the 調整 table at the top.
  // (a plain-string name is a substring match — terms like "頭痛(重度)" are not regex-safe)
  const audit = page.locator("section", {
    has: page.getByRole("heading", { name: /レビュー・承認（HITL）/ }),
  });
  const row = audit.getByRole("row", { name: ov.term }).filter({ hasText: ov.rationale });
  await expect(row).toContainText(original);
  await expect(row).toContainText(ov.new_verdict);
  await expect(page.getByText("approved · 承認済み")).toBeVisible();
});

test("a case with no own-company product is gated out, with no review form", async ({ page }) => {
  await runSample(page, "症例004");

  await expect(page.getByText("out of scope · 評価対象外")).toBeVisible();
  await expect(page.getByText("自社品が使用されていないため、評価は実行されません")).toBeVisible();
  await expect(page.getByRole("button", { name: "承認する" })).toHaveCount(0);
});
