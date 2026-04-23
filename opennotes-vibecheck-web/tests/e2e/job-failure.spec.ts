import { test, expect } from "@playwright/test";
import {
  LINKEDIN_BLOCKED_URL,
  submitUrlAndWaitForAnalyze,
} from "./fixtures/quizlet";

/**
 * AC3 — Inline job failure
 *
 * Submitting `https://linkedin.com/feed/` should produce an
 * `unsupported_site` failure. The failure card MUST render inline
 * on `/analyze` (no automatic redirect back to `/`), it MUST mention
 * `linkedin.com`, and the "Try again" affordance MUST be present.
 */
test("AC3: linkedin.com submit shows inline failure card with Try again, no home redirect", async ({
  page,
}) => {
  test.setTimeout(60_000);

  const { jobId, pendingError } = await submitUrlAndWaitForAnalyze(
    page,
    LINKEDIN_BLOCKED_URL,
  );

  // Pre-job failures (unsupported_site etc.) come back as a server-side
  // redirect carrying ?pending_error so the route renders the failure
  // card without ever creating a job_id. Either path is acceptable as
  // long as we land on /analyze (no redirect to /).
  expect(
    new URL(page.url()).pathname,
    "Failure must render inline on /analyze, never bounce home",
  ).toBe("/analyze");

  if (jobId) {
    // job_id path: poll resource will report the failure asynchronously.
  } else {
    expect(
      pendingError,
      "Without a job_id, /analyze should carry a ?pending_error so the failure card renders synchronously",
    ).toBeTruthy();
  }

  const failureCard = page.locator('[data-testid="job-failure-card"]');
  await expect(failureCard).toBeVisible({ timeout: 30_000 });

  // The failure copy or URL fragment must reference linkedin.com so users
  // can immediately understand which site was rejected.
  const cardText = (await failureCard.textContent())?.toLowerCase() ?? "";
  expect(cardText).toContain("linkedin.com");

  // Try-again form is present and stays put (it submits to the analyze
  // action; we only assert visibility, not the actual click).
  await expect(
    page.locator('[data-testid="job-failure-try-again"]'),
  ).toBeVisible();

  // Hard guard: even after a brief pause the page must not navigate
  // back to home.
  await page.waitForTimeout(1_000);
  expect(new URL(page.url()).pathname).toBe("/analyze");
});
