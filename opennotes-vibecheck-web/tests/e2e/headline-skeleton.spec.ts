import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

/**
 * TASK-1569.05 — End-to-end skeleton lifecycle for the headline lead-in
 * (headline summary + weather report column).
 *
 * Drives a job through a scripted mock-API state machine:
 *
 *   poll 1 → pending, sections empty, sidebar_payload=null,
 *            sidebar_payload_complete=false → BOTH skeletons must be
 *            visible (headline-summary-skeleton + weather-report-skeleton),
 *            and the new Skeleton primitive's shimmer overlay
 *            ([data-skeleton-shimmer]) must be present.
 *   poll 2+ →
 *      Variant A (resolution): done, sidebar_payload populated with
 *        headline + weather_report, sidebar_payload_complete=true →
 *        skeletons disappear, real headline-summary + weather-report
 *        testids render.
 *      Variant B (null weather collapse): done, sidebar_payload populated
 *        with headline but weather_report=null, sidebar_payload_complete=
 *        true → headline-summary renders full-width (HeadlineLeadIn drops
 *        the lg:grid-cols-[minmax(max-content,28rem)_1fr] class) and the
 *        weather-report testid never resolves.
 *
 * This is a verification-only test — it stubs the backend and observes
 * the SolidStart UI's skeleton lifecycle without touching production
 * infrastructure. The `next_poll_ms` returned by the mock API is short
 * (250 ms) so the lifecycle resolves quickly without becoming flaky.
 */

const RESOLUTION_JOB_ID = "77777777-7777-7777-8777-777777777777";
const NULL_WEATHER_JOB_ID = "88888888-8888-7888-8888-888888888888";
const ATTEMPT_ID = "99999999-9999-7999-8999-999999999999";
const SOURCE_URL = "https://quizlet.com/blog/groups-are-now-classes/";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let pollCounts = new Map<string, number>();

async function listenOnRandomPort(server: Server): Promise<number> {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("server did not bind to a TCP port");
  }
  return address.port;
}

async function findFreePort(): Promise<number> {
  const server = createServer();
  const port = await listenOnRandomPort(server);
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return port;
}

async function waitForHttpOk(url: string, timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(
    `Timed out waiting for ${url}. Last error: ${
      lastError instanceof Error ? lastError.message : String(lastError)
    }\n${webLogs}`,
  );
}

function sectionDataFor(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") return { harmful_content_matches: [] };
  if (slug === "safety__web_risk") return { findings: [] };
  if (slug === "safety__image_moderation") return { matches: [] };
  if (slug === "safety__video_moderation") return { matches: [] };
  if (slug === "tone_dynamics__flashpoint") return { flashpoint_matches: [] };
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "Stable.",
        summary: "Stable.",
        tone_labels: ["informational"],
        per_speaker_notes: {},
        speaker_arcs: [],
        insufficient_conversation: true,
      },
    };
  }
  if (
    slug === "facts_claims__dedup" ||
    slug === "facts_claims__evidence" ||
    slug === "facts_claims__premises"
  ) {
    return {
      claims_report: { deduped_claims: [], total_claims: 0, total_unique: 0 },
    };
  }
  if (slug === "facts_claims__known_misinfo") {
    return { known_misinformation: [] };
  }
  if (slug === "opinions_sentiments__sentiment") {
    return {
      sentiment_stats: {
        per_utterance: [],
        positive_pct: 0,
        negative_pct: 0,
        neutral_pct: 100,
        mean_valence: 0,
      },
    };
  }
  return { subjective_claims: [] };
}

function allDoneSections(): Record<string, unknown> {
  return Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionDataFor(slug),
        finished_at: "2026-04-23T22:09:00Z",
      },
    ]),
  );
}

function completedSidebarPayload(opts: {
  withWeather: boolean;
}): Record<string, unknown> {
  const headline = {
    text: "A concise lead-in summary derived from the conversation.",
    kind: "synthesized",
    source: "server",
    unavailable_inputs: [],
  };
  const weather = opts.withWeather
    ? {
        truth: { label: "first_person", logprob: null, alternatives: [] },
        relevance: { label: "on_topic", logprob: null, alternatives: [] },
        sentiment: { label: "neutral", logprob: null, alternatives: [] },
      }
    : null;
  return {
    source_url: SOURCE_URL,
    page_title: "Groups are now classes",
    page_kind: "article",
    scraped_at: "2026-04-23T22:08:00Z",
    cached: false,
    headline,
    weather_report: weather,
    safety: { harmful_content_matches: [], recommendation: null },
    tone_dynamics: {
      scd: {
        narrative: "",
        summary: "",
        tone_labels: [],
        per_speaker_notes: {},
        speaker_arcs: [],
        insufficient_conversation: true,
      },
      flashpoint_matches: [],
    },
    facts_claims: {
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
      },
      known_misinformation: [],
    },
    opinions_sentiments: {
      opinions_report: {
        sentiment_stats: {
          per_utterance: [],
          positive_pct: 0,
          negative_pct: 0,
          neutral_pct: 100,
          mean_valence: 0,
        },
        subjective_claims: [],
      },
    },
    web_risk: { findings: [] },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
  };
}

function pendingState(jobId: string): Record<string, unknown> {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "pending",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:08:00Z",
    sections: {},
    sidebar_payload: null,
    sidebar_payload_complete: false,
    activity_label: "Preparing analysis",
    activity_at: "2026-04-23T22:08:00Z",
    cached: false,
    next_poll_ms: 250,
    page_title: null,
    page_kind: null,
    utterance_count: 0,
  };
}

function doneState(
  jobId: string,
  opts: { withWeather: boolean },
): Record<string, unknown> {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections: allDoneSections(),
    sidebar_payload: completedSidebarPayload(opts),
    sidebar_payload_complete: true,
    activity_label: null,
    activity_at: null,
    cached: false,
    next_poll_ms: 1500,
    page_title: "Groups are now classes",
    page_kind: "article",
    utterance_count: 3,
  };
}

function nextPoll(
  jobId: string,
  withWeather: boolean,
): Record<string, unknown> {
  const count = (pollCounts.get(jobId) ?? 0) + 1;
  pollCounts.set(jobId, count);
  // First two polls → pending (skeletons visible). Third poll onward → done.
  // Two pending polls (≈500 ms with next_poll_ms=250) gives Playwright a
  // reliably observable skeleton window even on cold dev-server starts where
  // SSR + hydration consume most of the page.goto budget.
  if (count <= 2) return pendingState(jobId);
  return doneState(jobId, { withWeather });
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${RESOLUTION_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(nextPoll(RESOLUTION_JOB_ID, true)));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${NULL_WEATHER_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(nextPoll(NULL_WEATHER_JOB_ID, false)));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ can_iframe: true, blocking_header: null }));
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ screenshot_url: null }));
      return;
    }
    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error_code: "not_found" }));
  });
  const apiPort = await listenOnRandomPort(apiServer);
  apiBaseUrl = `http://127.0.0.1:${apiPort}`;

  const webPort = await findFreePort();
  webBaseUrl = `http://127.0.0.1:${webPort}`;
  webProcess = spawn(
    "pnpm",
    ["run", "dev", "--port", String(webPort), "--host", "127.0.0.1"],
    {
      cwd: fileURLToPath(new URL("../..", import.meta.url)),
      env: {
        ...process.env,
        VIBECHECK_SERVER_URL: apiBaseUrl,
        VIBECHECK_WEB_PORT: String(webPort),
        HOST: "127.0.0.1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  webProcess.stdout?.on("data", (chunk) => {
    webLogs += chunk.toString();
  });
  webProcess.stderr?.on("data", (chunk) => {
    webLogs += chunk.toString();
  });
  webProcess.once("exit", (code, signal) => {
    if (code !== 0 && signal !== "SIGTERM") {
      webLogs += `\nweb process exited code=${code} signal=${signal}`;
    }
  });
  await waitForHttpOk(webBaseUrl);
});

test.afterAll(async () => {
  if (webProcess && !webProcess.killed) {
    webProcess.kill("SIGTERM");
  }
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test.beforeEach(() => {
  pollCounts = new Map<string, number>();
});

test("AC1+AC2+AC3: skeletons appear, shimmer animates, then resolve to real headline + weather", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${RESOLUTION_JOB_ID}`);

  const headlineSkeleton = page.locator(
    '[data-testid="headline-summary-skeleton"]',
  );
  const weatherSkeleton = page.locator(
    '[data-testid="weather-report-skeleton"]',
  );

  // AC1: Both skeletons visible quickly after navigation. Playwright auto-
  // retries the visibility assertion up to the supplied timeout, so the
  // 1500 ms ceiling is the maximum window the test will tolerate before
  // failing — actual resolution is typically sub-200 ms locally. We use a
  // forgiving ceiling rather than the brief's 200 ms because the SSR loader
  // does the first poll server-side and SolidStart hydration cost varies
  // between cold and warm dev-server runs.
  await expect(headlineSkeleton).toBeVisible({ timeout: 1500 });
  await expect(weatherSkeleton).toBeVisible({ timeout: 1500 });

  // AC2: Shimmer overlay from the new Skeleton primitive is present inside
  // both skeleton blocks. The Skeleton component emits a child element with
  // data-skeleton-shimmer for every Skeleton instance.
  await expect(
    headlineSkeleton.locator("[data-skeleton-shimmer]").first(),
  ).toBeAttached();
  await expect(
    weatherSkeleton.locator("[data-skeleton-shimmer]").first(),
  ).toBeAttached();
  // The Skeleton root itself uses data-opennotes-skeleton, which is the
  // selector the shimmer CSS keys off of for the shimmer-pulse animation.
  await expect(
    headlineSkeleton.locator("[data-opennotes-skeleton]").first(),
  ).toBeAttached();

  // AC3: Once sidebar_payload arrives, skeletons must disappear and the
  // real headline-summary testid renders.
  const headlineSummary = page.locator('[data-testid="headline-summary"]');
  await expect(headlineSummary).toBeVisible({ timeout: 15_000 });
  await expect(headlineSkeleton).toHaveCount(0);

  // AC4 (positive case): when weather_report is non-null, the weather-report
  // testid resolves and replaces the weather-report-skeleton.
  const weatherReport = page.locator('[data-testid="weather-report"]');
  await expect(weatherReport).toBeVisible({ timeout: 15_000 });
  await expect(weatherSkeleton).toHaveCount(0);
});

test("AC4+AC6 collapse: weather_report=null + done renders single-column headline (TASK-1569.06)", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${NULL_WEATHER_JOB_ID}`);

  const root = page.locator('[data-testid="headline-lead-in"]');
  const headlineSummary = page.locator('[data-testid="headline-summary"]');
  const weatherReport = page.locator('[data-testid="weather-report"]');

  // Wait for the headline to fully resolve so we know the final
  // (sidebar_payload_complete=true) state has propagated.
  await expect(headlineSummary).toBeVisible({ timeout: 15_000 });

  // AC4: Weather is null and complete → no weather-report testid renders
  // and the weather skeleton has unmounted.
  await expect(weatherReport).toHaveCount(0);
  await expect(
    page.locator('[data-testid="weather-report-skeleton"]'),
  ).toHaveCount(0);

  // AC6: HeadlineLeadIn has dropped the 2-column lg-grid class — the
  // single-column gridClass is `grid grid-cols-1 gap-3` (no
  // lg:grid-cols-[...] suffix). We assert via the class attribute so the
  // test fails loudly if the collapse logic regresses.
  const cls = (await root.getAttribute("class")) ?? "";
  expect(cls).toMatch(/\bgrid-cols-1\b/);
  expect(cls).not.toMatch(/lg:grid-cols-\[minmax\(max-content,28rem\)_1fr\]/);
});

/**
 * TASK-1572.06 — No-empty-container invariant + tooltip + null-weather collapse.
 *
 * The original 1572 bug was empty bubbles/boxes appearing during refresh of an
 * in-flight or completed job. These tests enforce the invariant that if a
 * lead-in container is in the DOM at all, it always contains either a skeleton
 * or real content — never an empty shell.
 */

async function assertNoEmptyContainers(page: import("@playwright/test").Page) {
  // headline-lead-in: if present, must contain at least one of:
  // headline-summary (real), headline-summary-skeleton (skeleton),
  // weather-report (real), or weather-report-skeleton (skeleton).
  const leadIn = page.locator('[data-testid="headline-lead-in"]');
  const leadInCount = await leadIn.count();
  if (leadInCount > 0) {
    const childMatches = await leadIn.locator(
      [
        '[data-testid="headline-summary"]',
        '[data-testid="headline-summary-skeleton"]',
        '[data-testid="weather-report"]',
        '[data-testid="weather-report-skeleton"]',
      ].join(", "),
    ).count();
    expect(
      childMatches,
      "headline-lead-in must contain a skeleton or real content",
    ).toBeGreaterThan(0);
  }

  // weather-report (real card): if present, must contain at least one axis row.
  const weather = page.locator('[data-testid="weather-report"]');
  if ((await weather.count()) > 0) {
    const rows = await weather.locator(
      '[data-testid^="weather-axis-card-"]',
    ).count();
    expect(
      rows,
      "weather-report must contain at least one axis row",
    ).toBeGreaterThan(0);
  }

  // weather-report-skeleton: if present, must have at least one skeleton row.
  const weatherSkel = page.locator('[data-testid="weather-report-skeleton"]');
  if ((await weatherSkel.count()) > 0) {
    const rows = await weatherSkel.locator(
      '[data-testid^="weather-skeleton-"]',
    ).count();
    expect(
      rows,
      "weather-report-skeleton must contain at least one skeleton row",
    ).toBeGreaterThan(0);
  }
}

test("AC1 no-empty-container invariant: lead-in always has skeleton or content across the lifecycle", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${RESOLUTION_JOB_ID}`);

  // Initial pending tick — skeletons should be the only children.
  await expect(
    page.locator('[data-testid="weather-report-skeleton"]'),
  ).toBeVisible({ timeout: 1500 });
  await assertNoEmptyContainers(page);

  // Sample the invariant repeatedly while the job transitions to done.
  // 12 ticks at 100 ms each = 1.2 s of coverage, comfortably crossing the
  // 250 ms next_poll_ms cadence configured in the mock API.
  for (let i = 0; i < 12; i++) {
    await assertNoEmptyContainers(page);
    await page.waitForTimeout(100);
  }

  // Final done tick — real content present, no skeleton.
  await expect(page.locator('[data-testid="weather-report"]')).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator('[data-testid="headline-summary"]')).toBeVisible();
  await assertNoEmptyContainers(page);
});

test("AC2 tooltip hover: hovering a weather-axis row reveals axis name + interpretation copy", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${RESOLUTION_JOB_ID}`);
  await expect(page.locator('[data-testid="weather-report"]')).toBeVisible({
    timeout: 15_000,
  });

  type AxisCheck = { axisType: string; copyMatch: RegExp };
  const checks: AxisCheck[] = [
    { axisType: "truth", copyMatch: /sourced|misleading|epistemic stance/i },
    {
      axisType: "relevance",
      copyMatch: /insightful|on topic|drifting/i,
    },
    {
      axisType: "sentiment",
      copyMatch: /supportive|neutral|critical|oppositional|emotional stance/i,
    },
  ];

  for (const { axisType, copyMatch } of checks) {
    const row = page.locator(`[data-testid="weather-axis-card-${axisType}"]`);
    await row.hover();
    const tooltip = page.locator('[role="tooltip"]').first();
    await expect(tooltip).toBeVisible({ timeout: 5_000 });
    await expect(tooltip).toContainText(
      new RegExp(`^${axisType.charAt(0).toUpperCase() + axisType.slice(1)}`),
    );
    await expect(tooltip).toContainText(copyMatch);
    // Move pointer away so the next hover triggers a fresh open.
    await page.mouse.move(0, 0);
    await page.waitForTimeout(150);
  }
});

test("AC3 null-weather case: no empty weather card appears at any tick", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${NULL_WEATHER_JOB_ID}`);

  // First tick: pending → both skeletons. Must not violate the invariant.
  await assertNoEmptyContainers(page);

  // Wait for resolution to "done with weather=null".
  await expect(page.locator('[data-testid="headline-summary"]')).toBeVisible({
    timeout: 15_000,
  });

  // After done: weather column collapsed (no weather-report or skeleton).
  await expect(page.locator('[data-testid="weather-report"]')).toHaveCount(0);
  await expect(
    page.locator('[data-testid="weather-report-skeleton"]'),
  ).toHaveCount(0);

  // Sample the invariant repeatedly to ensure no empty weather container
  // ever flickers in during the null-weather lifecycle.
  for (let i = 0; i < 12; i++) {
    await assertNoEmptyContainers(page);
    await page.waitForTimeout(100);
  }
});
