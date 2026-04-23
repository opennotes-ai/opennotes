import { test, expect } from "@playwright/test";
import {
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
} from "./fixtures/quizlet";

/**
 * AC5 — Polling rate-limit
 *
 * Fire a tight burst of concurrent polls against `/api/analyze/{job_id}`
 * and verify we observe at least one 429 response with a `Retry-After`
 * header. The vibecheck-server documents both burst and sustained
 * limits per `(ip, job_id)`, so a burst from one runner against one
 * job is sufficient to trip them.
 *
 * We use Playwright's `APIRequestContext` (`request`) rather than
 * `page.evaluate` + browser `fetch`. The FastAPI app does not install
 * CORS middleware, so a same-tab cross-origin browser fetch from the
 * web app's origin to the upstream API would be rejected by the
 * browser before we ever see the upstream's status code. The Node-side
 * request context bypasses CORS and hits the server directly, exactly
 * like a programmatic client would.
 */

const API_BASE_URL =
  process.env.VIBECHECK_E2E_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_COUNT = Number(
  process.env.VIBECHECK_E2E_RATE_LIMIT_REQUESTS ?? "30",
);

test("AC5: rapid polling produces 429 responses with Retry-After", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);

  const { jobId } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(jobId, "Need a real job_id to exercise the per-job limiter").toBeTruthy();

  const url = `${API_BASE_URL.replace(/\/$/, "")}/api/analyze/${jobId}`;
  const start = Date.now();
  const responses = await Promise.allSettled(
    Array.from({ length: REQUEST_COUNT }, () => request.get(url)),
  );
  const elapsedMs = Date.now() - start;

  const statuses: number[] = [];
  let retryAfter: string | null = null;
  let errors = 0;
  for (const r of responses) {
    if (r.status === "fulfilled") {
      const status = r.value.status();
      statuses.push(status);
      if (status === 429 && retryAfter === null) {
        retryAfter = r.value.headers()["retry-after"] ?? null;
      }
    } else {
      errors += 1;
    }
  }

  expect(
    elapsedMs,
    `Burst should complete quickly — took ${elapsedMs}ms`,
  ).toBeLessThan(15_000);

  const histogram = statuses.reduce<Record<number, number>>((acc, s) => {
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});
  const status429 = histogram[429] ?? 0;
  expect(
    status429,
    `Expected at least one 429 response from ${REQUEST_COUNT} concurrent polls (statuses observed: ${JSON.stringify(
      histogram,
    )}, errors: ${errors})`,
  ).toBeGreaterThan(0);

  expect(
    retryAfter,
    "429 response should carry a Retry-After header so the polling client can back off",
  ).not.toBeNull();
});
