import { test, expect, type Page } from "@playwright/test";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

async function expectNoDirectVisitLoadingIndicators(page: Page) {
  await page.waitForSelector('[data-testid="analyze-layout"]', {
    timeout: 5_000,
  });

  await expect(page.locator('[data-testid="extracting-indicator"]')).toHaveCount(
    0,
  );
  await expect(page.locator('[data-testid="page-frame-loading"]')).toHaveCount(
    0,
  );
}

test("direct visit to cached done job (no c=1) shows no extracting/loading indicators", async ({
  page,
}) => {
  test.setTimeout(220_000);

  const first = await submitUrlAndWaitForAnalyze(page, QUIZLET_REFERENCE_URL);
  expect(first.jobId, "First submit must produce a job_id").toBeTruthy();
  await waitForAllSectionsTerminal(page, { timeoutMs: 180_000 });

  const jobId = first.jobId!;
  await page.goto(`/analyze?job=${encodeURIComponent(jobId)}`);

  const url = new URL(page.url());
  expect(url.searchParams.get("c")).toBeNull();

  await expectNoDirectVisitLoadingIndicators(page);

  const states = await waitForAllSectionsTerminal(page, {
    timeoutMs: 500,
    pollIntervalMs: 50,
  });
  for (const slug of ALL_SECTION_SLUGS) {
    expect(
      states[slug],
      `Expected ${slug} to be terminal within the direct cached revisit budget`,
    ).toMatch(/^(done|failed)$/);
  }
});
