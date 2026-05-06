import { test, expect } from "@playwright/test";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

/**
 * AC2 — Cache-hit no-flash
 *
 * The first submit may go cold; we wait for it to finish so the URL is
 * cached. The second submit MUST hit the cache (the action redirects
 * with `?c=1`). On that second navigation the skeleton container must
 * be invisible at t=0 (no flash) and content must land within 500ms.
 *
 * The DOM contract is `data-cached-hint="1"` on each `slot-<slug>`
 * which combined with the app.css rule:
 *
 *   [data-cached-hint="1"] .skeleton-pulse { opacity: 0; }
 *
 * yields opacity:0 on every skeleton-pulse element until the section
 * payload arrives. We assert this via `getComputedStyle().opacity`.
 */
test("AC2: cache-hit second submit shows no skeleton flash and resolves <500ms", async ({
  page,
}) => {
  test.setTimeout(220_000);

  // Warm the cache.
  const first = await submitUrlAndWaitForAnalyze(page, QUIZLET_REFERENCE_URL);
  expect(first.jobId, "First submit must produce a job_id").toBeTruthy();
  await waitForAllSectionsTerminal(page, { timeoutMs: 180_000 });

  // Second submit — must come back cached. The home action redirects
  // synchronously from the server before the page paints, so we measure
  // skeleton opacity as soon as /analyze is committed.
  const t0 = Date.now();
  const second = await submitUrlAndWaitForAnalyze(page, QUIZLET_REFERENCE_URL);
  expect(second.jobId, "Second submit must produce a job_id").toBeTruthy();

  const url = new URL(page.url());
  expect(
    url.searchParams.get("c"),
    "Second submit must be flagged as cached via ?c=1",
  ).toBe("1");

  // Capture the skeleton opacity before the polling loop has had time
  // to flip slot states. Even if the layout is mounted with `running`
  // skeletons, the data-cached-hint="1" CSS rule must keep their
  // opacity at 0 — the operative no-flash invariant.
  await page.waitForSelector('[data-testid="analyze-layout"]', {
    timeout: 5_000,
  });

  const skeletonOpacities = await page.evaluate((slugs) => {
    const samples: Array<{ slug: string; opacity: string; count: number }> = [];
    for (const slug of slugs) {
      const slot = document.querySelector(
        `[data-testid="slot-${slug}"]`,
      ) as HTMLElement | null;
      if (!slot) {
        samples.push({ slug, opacity: "no-slot", count: 0 });
        continue;
      }
      const pulses = slot.querySelectorAll(".skeleton-pulse");
      if (pulses.length === 0) {
        samples.push({ slug, opacity: "no-pulse", count: 0 });
        continue;
      }
      const first = pulses[0] as HTMLElement;
      samples.push({
        slug,
        opacity: getComputedStyle(first).opacity,
        count: pulses.length,
      });
    }
    return samples;
  }, ALL_SECTION_SLUGS as unknown as string[]);

  // Two valid no-flash outcomes for a cache-hit:
  //   1. No .skeleton-pulse renders at all (cached payload SSR'd as `done`).
  //   2. Skeletons render briefly but data-cached-hint="1" pins opacity to 0.
  //
  // The vacuous failure mode the brief flagged is when EVERY sample has
  // count === 0 AND we never assert anything. If skeletons exist anywhere,
  // they MUST be at opacity 0; if skeletons don't exist anywhere, that is
  // itself a valid no-flash result and we record it explicitly.
  const samplesWithSkeleton = skeletonOpacities.filter((s) => s.count > 0);
  if (samplesWithSkeleton.length === 0) {
    const allSlotStates = await page.evaluate((slugs) => {
      const out: Record<string, string> = {};
      for (const slug of slugs) {
        const el = document.querySelector(
          `[data-testid="slot-${slug}"]`,
        ) as HTMLElement | null;
        out[slug] = el?.dataset.slotState ?? "absent";
      }
      return out;
    }, ALL_SECTION_SLUGS as unknown as string[]);
    expect(
      Object.values(allSlotStates).every(
        (state) => state === "done" || state === "failed",
      ),
      `Cache-hit produced zero skeletons, which is only valid when every slot is already terminal (states: ${JSON.stringify(allSlotStates)})`,
    ).toBe(true);
  } else {
    for (const sample of samplesWithSkeleton) {
      expect(
        Number(sample.opacity),
        `Skeleton for ${sample.slug} must have opacity 0 on cache-hit (got ${sample.opacity})`,
      ).toBe(0);
    }
  }

  // Content must land within 500ms — assert at least one slot reaches
  // `done` within the budget. We poll the DOM rather than waiting on a
  // network signal because the cached payload may already be present
  // in the SSR render.
  const start = Date.now();
  let observed = false;
  while (Date.now() - start < 500) {
    const doneCount = await page.evaluate((slugs) => {
      let count = 0;
      for (const slug of slugs) {
        const el = document.querySelector(
          `[data-testid="slot-${slug}"]`,
        ) as HTMLElement | null;
        if (el?.dataset.slotState === "done") count += 1;
      }
      return count;
    }, ALL_SECTION_SLUGS as unknown as string[]);
    if (doneCount === ALL_SECTION_SLUGS.length) {
      observed = true;
      break;
    }
    await page.waitForTimeout(25);
  }

  const elapsedSinceSubmit = Date.now() - t0;
  expect(
    observed,
    `Cache-hit content must reach 'done' on all ${ALL_SECTION_SLUGS.length} slots within 500ms after navigation (elapsed ${elapsedSinceSubmit}ms)`,
  ).toBe(true);
});
