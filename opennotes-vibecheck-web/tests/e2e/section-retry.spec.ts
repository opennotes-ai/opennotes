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
 * hook today (no `X-Vibecheck-Test-Fail`, no `VIBECHECK_E2E_FAIL_SLUG`
 * env, etc. — see TASK-1473.34 follow-up). To exercise the retry UI in
 * a real browser without a backend hook we intercept the SolidStart
 * server-action response that powers the polling resource and rewrite
 * the slot's `state` to `failed` for a single slug. Once Retry is
 * clicked we let the natural response through again and assert the
 * slot recovers to `done`.
 *
 * The injected slug is `safety__moderation` because it's typically the
 * fastest section to complete in the live pipeline, which keeps the
 * test bounded.
 */

const TARGET_SLUG = "safety__moderation";

interface JobStatePayload {
  status?: string;
  sections?: Record<string, { state?: string; attempt_id?: string }>;
  [key: string]: unknown;
}

function rewriteSlotToFailed(body: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return body;
  }
  // SolidStart wraps action/query results — they may surface as
  // `{ data: ... }`, as a top-level JobState, or inside an array with
  // a marker frame. Walk the structure and rewrite any object that
  // looks like a JobState.
  const visit = (node: unknown): unknown => {
    if (!node || typeof node !== "object") return node;
    if (Array.isArray(node)) return node.map(visit);
    const obj = node as Record<string, unknown>;
    const looksLikeJobState =
      "sections" in obj &&
      obj.sections &&
      typeof obj.sections === "object";
    if (looksLikeJobState) {
      const cast = obj as JobStatePayload;
      const sections = { ...(cast.sections ?? {}) };
      const existing = sections[TARGET_SLUG] ?? { attempt_id: "injected" };
      sections[TARGET_SLUG] = {
        ...existing,
        state: "failed",
        attempt_id: existing.attempt_id ?? "injected",
      };
      return { ...obj, sections };
    }
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) out[k] = visit(v);
    return out;
  };
  return JSON.stringify(visit(parsed));
}

async function maybeRewriteJobStateResponse(
  route: Route,
  shouldRewrite: () => boolean,
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
  const newBody = shouldRewrite() ? rewriteSlotToFailed(body) : body;
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

  await page.route("**/*", (route) =>
    maybeRewriteJobStateResponse(route, () => injectFailure),
  );

  const { jobId } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(jobId).toBeTruthy();

  await expect(
    page.locator('[data-testid="analyze-layout"]'),
  ).toBeVisible({ timeout: 30_000 });

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
