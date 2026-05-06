import type { Page, Response } from "@playwright/test";

/**
 * Reference URL used by the golden-path / cache-hit specs.
 * The vibecheck spec calls out a Quizlet article as the canonical fixture
 * so the article is short, English-language, multi-speaker-friendly, and
 * unlikely to disappear.
 */
export const QUIZLET_REFERENCE_URL =
  process.env.VIBECHECK_E2E_QUIZLET_URL ??
  "https://quizlet.com/blog/groups-are-now-classes/";

/**
 * URL used by the inline-failure spec — LinkedIn is on the unsupported
 * site list, so the analyzer responds with an `unsupported_site` error
 * and the web app routes to /analyze with a `pending_error` query param.
 */
export const LINKEDIN_BLOCKED_URL = "https://linkedin.com/feed/";

export const ALL_SECTION_SLUGS = [
  "safety__moderation",
  "safety__web_risk",
  "safety__image_moderation",
  "safety__video_moderation",
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
  "facts_claims__dedup",
  "facts_claims__evidence",
  "facts_claims__premises",
  "facts_claims__known_misinfo",
  "opinions_sentiments__sentiment",
  "opinions_sentiments__subjective",
  "opinions_sentiments__trends_oppositions",
] as const;

export type SectionSlug = (typeof ALL_SECTION_SLUGS)[number];

/**
 * Submit a URL via the home page and wait for the navigation to /analyze.
 * Returns the job_id parsed out of the URL.
 */
export async function submitUrlAndWaitForAnalyze(
  page: Page,
  url: string,
): Promise<{ jobId: string | null; pendingError: string | null }> {
  await page.goto("/");
  await page.locator("#vibecheck-url").fill(url);
  await Promise.all([
    page.waitForURL((u) => u.pathname === "/analyze", { timeout: 30_000 }),
    page.locator('button[type="submit"]').click(),
  ]);
  const parsed = new URL(page.url());
  return {
    jobId: parsed.searchParams.get("job"),
    pendingError: parsed.searchParams.get("pending_error"),
  };
}

/**
 * Poll the DOM until every section slot has reached a terminal state
 * (`done` or `failed`), or until the deadline lapses. Returns the final
 * map of slug -> state so the caller can assert `done` count.
 *
 * We poll the DOM rather than waiting on network idle because the page
 * renders progressive updates as jobs complete, and individual sections
 * may flip to `done` at very different times.
 */
export async function waitForAllSectionsTerminal(
  page: Page,
  options: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<Record<SectionSlug, string>> {
  const timeoutMs = options.timeoutMs ?? 180_000;
  const pollIntervalMs = options.pollIntervalMs ?? 500;
  const deadline = Date.now() + timeoutMs;

  const TERMINAL = new Set(["done", "failed"]);
  const slugs = ALL_SECTION_SLUGS;

  while (Date.now() < deadline) {
    const states = await page.evaluate((slugList) => {
      const out: Record<string, string> = {};
      for (const slug of slugList) {
        const el = document.querySelector(
          `[data-testid="slot-${slug}"]`,
        ) as HTMLElement | null;
        out[slug] = el?.dataset.slotState ?? "absent";
      }
      return out;
    }, slugs as unknown as string[]);

    const allTerminal = slugs.every((s) => TERMINAL.has(states[s] ?? ""));
    if (allTerminal) return states as Record<SectionSlug, string>;

    await page.waitForTimeout(pollIntervalMs);
  }

  const finalStates = await page.evaluate((slugList) => {
    const out: Record<string, string> = {};
    for (const slug of slugList) {
      const el = document.querySelector(
        `[data-testid="slot-${slug}"]`,
      ) as HTMLElement | null;
      out[slug] = el?.dataset.slotState ?? "absent";
    }
    return out;
  }, slugs as unknown as string[]);

  throw new Error(
    `Timed out after ${timeoutMs}ms waiting for all sections to reach terminal state. ` +
      `Final states: ${JSON.stringify(finalStates)}`,
  );
}

/**
 * Wait until a specific section reaches the requested state.
 */
export async function waitForSectionState(
  page: Page,
  slug: SectionSlug,
  expectedState: "pending" | "running" | "done" | "failed",
  options: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<void> {
  const timeoutMs = options.timeoutMs ?? 180_000;
  const pollIntervalMs = options.pollIntervalMs ?? 500;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const state = await page.evaluate((s) => {
      const el = document.querySelector(
        `[data-testid="slot-${s}"]`,
      ) as HTMLElement | null;
      return el?.dataset.slotState ?? "absent";
    }, slug);
    if (state === expectedState) return;
    await page.waitForTimeout(pollIntervalMs);
  }

  throw new Error(
    `Timed out after ${timeoutMs}ms waiting for slot-${slug} to reach state '${expectedState}'.`,
  );
}

/**
 * Read the current per-slot state map without blocking.
 */
export async function readSectionStates(
  page: Page,
): Promise<Record<SectionSlug, string>> {
  return (await page.evaluate((slugList) => {
    const out: Record<string, string> = {};
    for (const slug of slugList) {
      const el = document.querySelector(
        `[data-testid="slot-${slug}"]`,
      ) as HTMLElement | null;
      out[slug] = el?.dataset.slotState ?? "absent";
    }
    return out;
  }, ALL_SECTION_SLUGS as unknown as string[])) as Record<SectionSlug, string>;
}

/**
 * Wait for the final job.status reported by the polling endpoint to hit
 * a terminal value. Useful when the test cares about the orchestration
 * outcome rather than per-slot UI state (e.g. cache-hit assertions).
 */
export async function waitForResponseStatus(
  page: Page,
  jobId: string,
  predicate: (status: number) => boolean,
  timeoutMs = 30_000,
): Promise<Response> {
  return page.waitForResponse(
    (response) => {
      if (!response.url().includes(`/api/analyze/${jobId}`)) return false;
      return predicate(response.status());
    },
    { timeout: timeoutMs },
  );
}
