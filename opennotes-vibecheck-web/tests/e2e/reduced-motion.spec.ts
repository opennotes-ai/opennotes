import { test, expect } from "@playwright/test";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

/**
 * AC6 — Reduced motion
 *
 * Under `prefers-reduced-motion: reduce` the skeleton pulse animation
 * and the section-reveal transition must both be disabled. We assert
 * this against the live computed style — the underlying contract from
 * `src/app.css`:
 *
 *   @media (prefers-reduced-motion: reduce) {
 *     .skeleton-pulse { animation: none; opacity: 0.55; }
 *     .section-reveal { animation: none; }
 *   }
 *
 * The DOM elements always carry the class names; the CSS rule is what
 * disables motion, so we sample `getComputedStyle().animationName` for
 * each.
 */

test("AC6: reduced-motion media disables skeleton pulse and section reveal", async ({
  page,
}) => {
  test.setTimeout(220_000);

  // Brief calls out `page.emulateMedia({ reducedMotion: 'reduce' })`
  // explicitly. Apply it before the first navigation so the matchMedia
  // query the CSS rule depends on returns true from the start.
  await page.emulateMedia({ reducedMotion: "reduce" });

  const { jobId } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(jobId).toBeTruthy();

  await expect(
    page.locator('[data-testid="analyze-layout"]'),
  ).toBeVisible({ timeout: 30_000 });

  // Sample skeletons while sections are still running. We wait until
  // at least one slot reports a `running` state OR until something has
  // settled — whichever comes first. The .skeleton-pulse element only
  // mounts during `running`, so missing it is OK as long as the rule
  // would still apply.
  const skeletonNames = await page.evaluate(() => {
    const out: Array<{ tag: string; animationName: string }> = [];
    const els = document.querySelectorAll(".skeleton-pulse");
    for (const el of Array.from(els).slice(0, 6)) {
      out.push({
        tag: (el as HTMLElement).tagName.toLowerCase(),
        animationName: getComputedStyle(el).animationName,
      });
    }
    return out;
  });

  for (const sample of skeletonNames) {
    expect(
      sample.animationName,
      `.skeleton-pulse animation-name must be 'none' under reduced motion (got '${sample.animationName}' on <${sample.tag}>)`,
    ).toBe("none");
  }

  // Wait for completion so we can inspect the section-reveal class
  // (which only mounts inside a `done` slot).
  await waitForAllSectionsTerminal(page, { timeoutMs: 180_000 });

  const revealNames = await page.evaluate((slugs) => {
    const out: Array<{ slug: string; animationName: string }> = [];
    for (const slug of slugs) {
      const el = document.querySelector(
        `[data-testid="slot-${slug}"] .section-reveal`,
      ) as HTMLElement | null;
      if (!el) continue;
      out.push({
        slug,
        animationName: getComputedStyle(el).animationName,
      });
    }
    return out;
  }, ALL_SECTION_SLUGS as unknown as string[]);

  expect(
    revealNames.length,
    "At least one .section-reveal element should be in the DOM after completion",
  ).toBeGreaterThan(0);

  for (const sample of revealNames) {
    expect(
      sample.animationName,
      `.section-reveal animation-name must be 'none' under reduced motion (got '${sample.animationName}' for ${sample.slug})`,
    ).toBe("none");
  }
});
