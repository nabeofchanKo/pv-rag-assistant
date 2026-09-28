import { expect, test } from "@playwright/test";
import approveRequest from "./fixtures/case_001.approve.request.json";
import draft from "./fixtures/case_001.draft.json";
import { en } from "../src/i18n/dictionaries/en";

// The English UI. Two things matter beyond "the words are English":
//   1. an English reader lands in English without doing anything, and
//   2. the English labels are only labels — what the review form SENDS is still
//      the Japanese values the API accepts. A mistranslated <option value> would
//      pass every visual check and then be rejected (or worse, accepted wrong).

const FAKE_BACKEND = "http://127.0.0.1:8765";

test.describe("with an English browser", () => {
  test.use({ locale: "en-US" });

  test("a bare link lands on the English triage page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/en\/triage$/);
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.getByRole("heading", { name: en.triage.title })).toBeVisible();
  });
});

test("the English review form shows English labels but sends Japanese values", async ({ page }) => {
  const ov = approveRequest.overrides[0];
  await page.goto("/en/triage");
  await page.getByRole("button", { name: /Case 001/ }).click();

  // Verdicts and MedDRA terms are in English; the case's own words are not.
  await expect(page.getByText(en.triage.status.awaiting_review)).toBeVisible();
  const headache = draft.meddra.find((m) => m.pt_name_en)!;
  await expect(page.getByText(headache.pt_name_en!, { exact: true }).first()).toBeVisible();

  // Pick the recorded override by its ENGLISH label.
  const label = en.vocab.values[ov.new_verdict as keyof typeof en.vocab.values]!;
  const axis = en.vocab.axis.seriousness;
  await page.getByPlaceholder(en.review.reviewerPlaceholder).fill(approveRequest.reviewer);
  await page.getByPlaceholder(en.review.notePlaceholder).fill(approveRequest.note);
  await page.getByLabel(en.review.newVerdictLabel(axis, ov.term)).selectOption({ label });
  await page.getByLabel(en.review.rationaleLabel(axis, ov.term)).fill(ov.rationale);
  await page.getByRole("button", { name: en.review.approve }).click();

  await expect(page.getByText(en.review.approvedBanner)).toBeVisible();
  const sent = await (await page.request.get(`${FAKE_BACKEND}/__last-approve`)).json();
  expect(sent.body).toEqual(approveRequest); // 要確認, not "Needs review"
});
