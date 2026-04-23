import { test, expect, type Route } from "@playwright/test";
import {
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForSectionState,
} from "./fixtures/quizlet";

/**
 * AC4 — Section-level retry
 *
 * Spec note: vibecheck-server has no first-class "inject failure" test
 * hook today. TASK-1473.35 tracks adding an `X-Vibecheck-Test-Fail-Slug`
 * request header that the orchestrator can honor server-side. Once that
 * lands, this proxy can be deleted in favor of:
 *
 *   await page.context().setExtraHTTPHeaders({
 *     "X-Vibecheck-Test-Fail-Slug": TARGET_SLUG,
 *   });
 *
 * Until then we intercept the polling response and rewrite a slot's
 * `state` to `failed` for the target slug. The rewriter is pinned to
 * the full JobState shape (`job_id`, `attempt_id`, `sections`) so a
 * silent payload-shape change does NOT result in a vacuous no-op test.
 * Before we begin asserting on UI state we assert that injection was
 * actually observed.
 *
 * The injected slug is `safety__moderation` because it's typically the
 * fastest section to complete in the live pipeline, which keeps the
 * test bounded.
 */

const TARGET_SLUG = "safety__moderation";

interface JobStatePayload {
  job_id: string;
  attempt_id: string;
  sections: Record<string, { state?: string; attempt_id?: string }>;
  [key: string]: unknown;
}

function isJobStateShape(obj: Record<string, unknown>): obj is JobStatePayload {
  return (
    typeof obj.job_id === "string" &&
    typeof obj.attempt_id === "string" &&
    obj.sections !== null &&
    typeof obj.sections === "object" &&
    !Array.isArray(obj.sections)
  );
}

function rewriteSlotToFailed(body: string): { body: string; rewrote: boolean } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return { body, rewrote: false };
  }
  let rewrote = false;
  const visit = (node: unknown): unknown => {
    if (!node || typeof node !== "object") return node;
    if (Array.isArray(node)) return node.map(visit);
    const obj = node as Record<string, unknown>;
    if (isJobStateShape(obj)) {
      const sections = { ...obj.sections };
      const existing = sections[TARGET_SLUG] ?? { attempt_id: "injected" };
      sections[TARGET_SLUG] = {
        ...existing,
        state: "failed",
        attempt_id: existing.attempt_id ?? "injected",
      };
      rewrote = true;
      return { ...obj, sections };
    }
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) out[k] = visit(v);
    return out;
  };
  const next = visit(parsed);
  return { body: JSON.stringify(next), rewrote };
}

async function maybeRewriteJobStateResponse(
  route: Route,
  shouldRewrite: () => boolean,
  onRewrite: () => void,
): Promise<void> {
  const url = route.request().url();
  const isPoll =
    /\/_server.*pollJobState/.test(url) ||
    /\/api\/analyze\/[^/]+(?:\?|$)/.test(url);
  if (!isPoll) {
    await route.fallback();
    return;
  }

  const response = await route.fetch();
  const status = response.status();
  if (status !== 200) {
    await route.fulfill({ response });
    return;
  }
  const headers = response.headers();
  const body = await response.text();
  if (!shouldRewrite()) {
    await route.fulfill({ status, headers, body });
    return;
  }
  const { body: newBody, rewrote } = rewriteSlotToFailed(body);
  if (rewrote) onRewrite();
  await route.fulfill({
    status,
    headers,
    body: newBody,
  });
}

test("AC4: section-level Retry recovers a failed slot to done", async ({
  page,
}) => {
  test.setTimeout(220_000);

  let injectFailure = true;
  let rewriteCount = 0;

  await page.route("**/*", (route) =>
    maybeRewriteJobStateResponse(
      route,
      () => injectFailure,
      () => {
        rewriteCount += 1;
      },
    ),
  );

  const { jobId } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(jobId).toBeTruthy();

  await expect(
    page.locator('[data-testid="analyze-layout"]'),
  ).toBeVisible({ timeout: 30_000 });

  // Confirm the proxy is actually observing JobState payloads BEFORE we
  // wait for `failed` state. If isJobStateShape() ever silently rejects
  // a renamed payload (e.g. job_id → jobId), waitForSectionState would
  // simply time out 180s later with no hint of why. Polling rewriteCount
  // surfaces the shape break directly with an actionable error.
  const injectionDeadline = Date.now() + 60_000;
  while (rewriteCount === 0 && Date.now() < injectionDeadline) {
    await page.waitForTimeout(250);
  }
  expect(
    rewriteCount,
    "Proxy must have rewritten at least one polling response — if this is 0 " +
      "the JobState payload shape likely changed (job_id/attempt_id/sections) " +
      "and the rewriter silently no-op'd. Update isJobStateShape() or migrate " +
      "to the X-Vibecheck-Test-Fail-Slug header from TASK-1473.35.",
  ).toBeGreaterThan(0);

  // Wait until the polling response carries a `failed` state for the
  // injected slug. We rely on the DOM rather than network introspection
  // because the SectionGroup re-renders as soon as the response is
  // applied.
  await waitForSectionState(page, TARGET_SLUG, "failed", {
    timeoutMs: 180_000,
  });

  const retryButton = page.locator(`[data-testid="retry-${TARGET_SLUG}"]`);
  await expect(retryButton, "Retry affordance must appear inline").toBeVisible({
    timeout: 5_000,
  });
  await expect(retryButton).toBeEnabled();

  // Stop injecting on the next polling response so when the polling
  // resource refetches after a successful retry, the natural
  // (`running` → `done`) state shines through.
  injectFailure = false;
  await retryButton.click();

  // Recovery: the slot should leave the `failed` state. We allow
  // either `running` or `done` as the next observable state — the
  // pipeline can complete fast enough that we never see `running`.
  const recovered = await Promise.race([
    waitForSectionState(page, TARGET_SLUG, "done", { timeoutMs: 180_000 }).then(
      () => "done" as const,
    ),
    waitForSectionState(page, TARGET_SLUG, "running", {
      timeoutMs: 30_000,
    }).then(() => "running" as const),
  ]);

  if (recovered === "running") {
    await waitForSectionState(page, TARGET_SLUG, "done", {
      timeoutMs: 180_000,
    });
  }

  // Final assertion — slot is done and Retry button is gone (since
  // RetryButton only renders inside the `failed` Match arm).
  await expect(
    page.locator(`[data-testid="retry-${TARGET_SLUG}"]`),
  ).toHaveCount(0);
});
