import { test, expect } from "@playwright/test";
import {
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
} from "./fixtures/quizlet";

/**
 * AC5 — Polling rate-limit
 *
 * Fire ~500 concurrent polls in <1s against `/api/analyze/{job_id}` and
 * verify we observe at least one 429 response with a `Retry-After`
 * header. The vibecheck-server documents both burst and sustained
 * limits per `(ip, job_id)`, so a tight burst from one tab against
 * one job is sufficient to trip them.
 *
 * The rate-limited endpoint is the upstream API. The browser-side
 * polling resource talks to the SolidStart server action, which in
 * turn calls the upstream — but we want to test the upstream guard
 * directly. We resolve the upstream URL by reading the
 * `VIBECHECK_E2E_API_BASE_URL` env var (default `http://localhost:8000`)
 * and use the browser's `fetch` so the IP that hits the limit is the
 * test runner's loopback, just like a real user's.
 */

const API_BASE_URL =
  process.env.VIBECHECK_E2E_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_COUNT = Number(
  process.env.VIBECHECK_E2E_RATE_LIMIT_REQUESTS ?? "500",
);

test("AC5: rapid polling produces 429 responses with Retry-After", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const { jobId } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(jobId, "Need a real job_id to exercise the per-job limiter").toBeTruthy();

  type FireResult = {
    statuses: number[];
    retryAfter: string | null;
    elapsedMs: number;
    fired: number;
    errors: number;
  };

  const result = await page.evaluate<FireResult, { base: string; jobId: string; n: number }>(
    async ({ base, jobId: id, n }) => {
      const url = `${base.replace(/\/$/, "")}/api/analyze/${id}`;
      const start = performance.now();
      const responses = await Promise.allSettled(
        Array.from({ length: n }, () =>
          fetch(url, {
            method: "GET",
            cache: "no-store",
            credentials: "omit",
            mode: "cors",
          }),
        ),
      );
      const statuses: number[] = [];
      let retryAfter: string | null = null;
      let errors = 0;
      for (const r of responses) {
        if (r.status === "fulfilled") {
          statuses.push(r.value.status);
          if (r.value.status === 429 && !retryAfter) {
            retryAfter = r.value.headers.get("Retry-After");
          }
        } else {
          errors += 1;
        }
      }
      return {
        statuses,
        retryAfter,
        elapsedMs: performance.now() - start,
        fired: n,
        errors,
      };
    },
    { base: API_BASE_URL, jobId: jobId!, n: REQUEST_COUNT },
  );

  expect(
    result.elapsedMs,
    `Burst should complete in roughly 1s — took ${result.elapsedMs.toFixed(0)}ms`,
  ).toBeLessThan(5_000);

  const status429 = result.statuses.filter((s) => s === 429).length;
  expect(
    status429,
    `Expected at least one 429 response from ${result.fired} concurrent polls (statuses observed: ${JSON.stringify(
      Object.fromEntries(
        Object.entries(
          result.statuses.reduce<Record<number, number>>((acc, s) => {
            acc[s] = (acc[s] ?? 0) + 1;
            return acc;
          }, {}),
        ),
      ),
    )}, errors: ${result.errors})`,
  ).toBeGreaterThan(0);

  expect(
    result.retryAfter,
    "429 response should carry a Retry-After header so the polling client can back off",
  ).not.toBeNull();
});
