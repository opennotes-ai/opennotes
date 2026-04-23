import { test, expect } from "@playwright/test";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

/**
 * AC1 — Golden path
 *
 * Submit a Quizlet URL → land on /analyze?job=<id> → verify each of the
 * 7 subsections transitions running → done. Allow up to 180s for the
 * whole pipeline. Poll the DOM rather than asserting on intermediate
 * timing — only the terminal state is load-bearing.
 */
test("AC1: golden-path Quizlet URL completes all 7 sections within 180s", async ({
  page,
}) => {
  test.setTimeout(200_000);

  const { jobId, pendingError } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(
    pendingError,
    "Submitting the canonical Quizlet URL must not produce a pending_error redirect",
  ).toBeNull();
  expect(jobId, "AnalyzePage must be reached with ?job=<id>").toBeTruthy();

  await expect(page.locator('[data-testid="analyze-layout"]')).toBeVisible({
    timeout: 30_000,
  });

  const finalStates = await waitForAllSectionsTerminal(page, {
    timeoutMs: 180_000,
  });

  const doneCount = ALL_SECTION_SLUGS.filter(
    (slug) => finalStates[slug] === "done",
  ).length;

  expect(
    doneCount,
    `All 7 sections must reach 'done' (got ${doneCount}: ${JSON.stringify(finalStates)})`,
  ).toBe(ALL_SECTION_SLUGS.length);

  await expect(
    page.locator('[data-testid="analyze-status"]'),
    "Status indicator should disappear once the job is done",
  ).toHaveCount(0);
});
