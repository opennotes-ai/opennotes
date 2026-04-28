import { test, expect } from "@playwright/test";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

/**
 * TASK-1508.04.05 — Headline summary E2E
 *
 * Submit the canonical Quizlet URL → wait for all 10 sections to reach
 * terminal → assert the headline summation block is rendered above the
 * safety recommendation, with non-empty text and a recognizable kind
 * discriminator (`stock` or `synthesized`). The headline is generated
 * server-side after the safety recommendation completes, so we only
 * inspect it after every section is terminal.
 *
 * The headline text shape (1-2 sentences, perceptive vs tabloid voice)
 * is judged by humans on the manual real-job verification pass — see
 * the task notes for the captured job IDs and observed text.
 *
 * Data-testids used (set by HeadlineSummaryReport.tsx):
 *   - data-testid="headline-summary"        (the section element)
 *   - data-testid="headline-summary-text"   (the inner <p>)
 *   - data-headline-kind                    ("stock" | "synthesized")
 *   - data-headline-source                  ("server" | "fallback")
 */
test("headline summation renders above safety-recommendation with non-empty text", async ({
  page,
}) => {
  test.setTimeout(220_000);

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
    `All 10 sections must reach 'done' before the headline lands (got ${doneCount}: ${JSON.stringify(finalStates)})`,
  ).toBe(ALL_SECTION_SLUGS.length);

  // The headline write happens after the safety_recommendation stage and
  // before finalize. Once finalize commits, the cached SidebarPayload the
  // poll endpoint serves carries the headline; the UI then renders it.
  // Poll for the testid rather than asserting immediately so we don't race
  // the orchestrator's post-finalize re-poll.
  const headline = page.getByTestId("headline-summary");
  await expect(headline, "headline summation block must render").toBeVisible({
    timeout: 30_000,
  });

  const text = page.getByTestId("headline-summary-text");
  const headlineText = (await text.textContent())?.trim() ?? "";
  expect(
    headlineText.length,
    `headline-summary-text must be non-empty (got: ${JSON.stringify(headlineText)})`,
  ).toBeGreaterThan(0);

  const kind = await headline.getAttribute("data-headline-kind");
  expect(
    kind,
    `data-headline-kind must be 'stock' or 'synthesized' (got: ${JSON.stringify(kind)})`,
  ).toMatch(/^(stock|synthesized)$/);

  const source = await headline.getAttribute("data-headline-source");
  expect(
    source,
    `data-headline-source must be 'server' after finalize (got: ${JSON.stringify(source)})`,
  ).toBe("server");

  // No ExpandableText affordance — the headline is plain text.
  await expect(
    text,
    "headline text must not render the read-more truncation chrome",
  ).not.toHaveAttribute("data-truncated", /.*/);

  // DOM order: headline-summary appears above safety-recommendation-report.
  // We assert the safety-recommendation block is visible first so a
  // regression that stops rendering it doesn't silently pass this spec.
  // compareDocumentPosition keeps the order assertion robust to wrappers
  // and small layout refactors.
  const safetyRec = page.getByTestId("safety-recommendation-report");
  await expect(
    safetyRec,
    "safety-recommendation-report must render alongside the headline so we can verify ordering",
  ).toBeVisible({ timeout: 10_000 });

  const headlinePrecedesSafety = await page.evaluate(() => {
    const h = document.querySelector('[data-testid="headline-summary"]');
    const s = document.querySelector(
      '[data-testid="safety-recommendation-report"]',
    );
    if (!h || !s) {
      return false;
    }
    // Node.DOCUMENT_POSITION_FOLLOWING (4) means s comes after h.
    return Boolean(
      h.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(
    headlinePrecedesSafety,
    "headline-summary must appear above safety-recommendation-report in the sidebar",
  ).toBe(true);
});
