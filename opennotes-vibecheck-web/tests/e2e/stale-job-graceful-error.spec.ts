import { test, expect } from "@playwright/test";

/**
 * Stale/unknown job_id — graceful in-page error, not root ErrorBoundary.
 *
 * When a user navigates directly to /analyze?job=<uuid-not-in-db>&c=1
 * the server returns 404 from `_error_response(404, "not_found", "job not found")`.
 * Before the TASK-1539 fix, this caused the root ErrorBoundary to surface with
 * "Something went wrong". After the fix, createAsync catches the rejection and
 * polling.ts handles the 404 via is404Error, showing JobFailureCard inline.
 *
 * "Graceful" means: the page stays on /analyze, no root error fallback appears,
 * and an inline failure card is shown to the user.
 */
test("stale job URL shows inline failure card, not root ErrorBoundary", async ({
  page,
}) => {
  test.setTimeout(30_000);

  const staleJobId = crypto.randomUUID();

  await page.goto(`/analyze?job=${encodeURIComponent(staleJobId)}&c=1`);

  expect(
    new URL(page.url()).pathname,
    "Must stay on /analyze, never redirect away",
  ).toBe("/analyze");

  await expect(
    page.getByText(/something went wrong/i),
    "Root ErrorBoundary fallback must not appear",
  ).toHaveCount(0);

  const failureCard = page.locator('[data-testid="job-failure-card"]');
  await expect(failureCard).toBeVisible({ timeout: 20_000 });

  expect(
    new URL(page.url()).pathname,
    "Must still be on /analyze after failure card appears",
  ).toBe("/analyze");
});
