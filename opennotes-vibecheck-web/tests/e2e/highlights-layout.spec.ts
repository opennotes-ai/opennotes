import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { createServer, type Server } from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));

const ATTEMPT_ID = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
const SOURCE_URL = "https://example.test/highlights-layout-test";

// Four job IDs — one per scenario in the AC matrix
const JOB_WEATHER_HIGHLIGHTS = "11111111-1111-7111-8111-111111111111";
const JOB_NO_WEATHER_HIGHLIGHTS = "22222222-2222-7222-8222-222222222222";
const JOB_WEATHER_NO_HIGHLIGHTS = "33333333-3333-7333-8333-333333333333";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";

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

function weatherReport(): Record<string, unknown> {
  return {
    truth: { label: "first_person", logprob: null, alternatives: [] },
    relevance: { label: "on_topic", logprob: null, alternatives: [] },
    sentiment: { label: "neutral", logprob: null, alternatives: [] },
  };
}

function headline(): Record<string, unknown> {
  return {
    text: "The discussion covers policy trade-offs with measured analytical framing.",
    kind: "synthesized",
    unavailable_inputs: [],
  };
}

function safetyWithDivergences(): Record<string, unknown> {
  return {
    harmful_content_matches: [],
    recommendation: {
      level: "caution",
      rationale: "Context escalated based on combined signals.",
      divergences: [
        {
          direction: "escalated",
          signal_source: "Text moderation",
          signal_detail: "Tone elevation in closing paragraph.",
          reason: "Elevated: sustained tone in context of policy debate.",
        },
      ],
    },
  };
}

function safetyNoHighlights(): Record<string, unknown> {
  return {
    harmful_content_matches: [],
    recommendation: null,
  };
}

function baseSidebarPayload(): Record<string, unknown> {
  return {
    cached_at: "2026-05-13T00:00:00Z",
    tone_dynamics: { flashpoint_matches: [] },
    facts_claims: {
      claims_report: { deduped_claims: [], total_claims: 0, total_unique: 0 },
      evidence_status: "done",
      premises_status: "done",
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
  };
}

function allDoneSections(): Record<string, unknown> {
  return Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: slug === "opinions_sentiments__highlights"
          ? { highlights_report: { highlights: [], fallback_engaged: false, floor_eligible_count: 0, total_input_count: 0 } }
          : {},
        finished_at: "2026-05-13T00:00:00Z",
      },
    ]),
  );
}

function jobState(
  jobId: string,
  extras: Record<string, unknown>,
): Record<string, unknown> {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-05-13T00:00:00Z",
    updated_at: "2026-05-13T00:00:00Z",
    sections: allDoneSections(),
    sidebar_payload: { ...baseSidebarPayload(), ...extras },
    sidebar_payload_complete: true,
    activity_label: null,
    activity_at: null,
    cached: true,
    next_poll_ms: 30_000,
    page_title: "Test article for highlights layout",
    page_kind: "article",
    utterance_count: 5,
  };
}

const JOB_RESPONSES: Record<string, Record<string, unknown>> = {
  [JOB_WEATHER_HIGHLIGHTS]: jobState(JOB_WEATHER_HIGHLIGHTS, {
    safety: safetyWithDivergences(),
    headline: headline(),
    weather_report: weatherReport(),
  }),
  [JOB_NO_WEATHER_HIGHLIGHTS]: jobState(JOB_NO_WEATHER_HIGHLIGHTS, {
    safety: safetyWithDivergences(),
    headline: headline(),
    weather_report: null,
  }),
  [JOB_WEATHER_NO_HIGHLIGHTS]: jobState(JOB_WEATHER_NO_HIGHLIGHTS, {
    safety: safetyNoHighlights(),
    headline: headline(),
    weather_report: weatherReport(),
  }),
};

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    const match = requestUrl.pathname.match(/^\/api\/analyze\/(.+)$/);
    if (request.method === "GET" && match) {
      const jobId = match[1];
      const data = JOB_RESPONSES[jobId];
      if (data) {
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify(data));
        return;
      }
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/frame-compat") {
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
      cwd: WEB_ROOT,
      env: {
        ...process.env,
        VIBECHECK_SERVER_URL: apiBaseUrl,
        VIBECHECK_WEB_PORT: String(webPort),
        HOST: "127.0.0.1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  webProcess.stdout?.on("data", (chunk: Buffer) => { webLogs += chunk.toString(); });
  webProcess.stderr?.on("data", (chunk: Buffer) => { webLogs += chunk.toString(); });
  webProcess.once("exit", (code: number | null, signal: string | null) => {
    if (code !== 0 && signal !== "SIGTERM") {
      webLogs += `\nweb process exited code=${code} signal=${signal}`;
    }
  });
  await waitForHttpOk(webBaseUrl);
});

test.afterAll(async () => {
  if (webProcess) await stopWebProcess(webProcess);
  if (apiServer) await new Promise<void>((resolve) => apiServer.close(() => resolve()));
});

test("AC1 desktop: 2-col layout — WeatherReport left, HeadlineSummary+HighlightsCard right", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_WEATHER_HIGHLIGHTS}`);
  await expect(page.getByTestId("analysis-sidebar")).toHaveAttribute(
    "data-job-status",
    "done",
    { timeout: 20_000 },
  );

  const leadIn = page.getByTestId("headline-lead-in");
  await expect(leadIn).toBeVisible();

  const chrome = page.getByTestId("headline-summary-chrome");
  const card = page.getByTestId("highlights-card");
  await expect(chrome).toBeVisible({ timeout: 10_000 });
  await expect(card).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("weather-report")).toBeVisible();

  const chromeBB = await chrome.boundingBox();
  const cardBB = await card.boundingBox();
  expect(chromeBB).not.toBeNull();
  expect(cardBB).not.toBeNull();
  expect(cardBB!.y).toBeGreaterThan(chromeBB!.y);

  const screenshotPath = testInfo.outputPath("ac1-desktop-2col-highlights.png");
  await page.screenshot({ path: screenshotPath, fullPage: false });
});

test("AC2 mobile: stack order WeatherReport → HeadlineSummary → HighlightsCard", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_WEATHER_HIGHLIGHTS}`);
  await expect(page.getByTestId("analysis-sidebar")).toHaveAttribute(
    "data-job-status",
    "done",
    { timeout: 20_000 },
  );

  await expect(page.getByTestId("weather-report")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("headline-summary-chrome")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("highlights-card")).toBeVisible({ timeout: 10_000 });

  const weatherBB = await page.getByTestId("weather-report").boundingBox();
  const headlineBB = await page.getByTestId("headline-summary-chrome").boundingBox();
  const highlightsBB = await page.getByTestId("highlights-card").boundingBox();
  expect(weatherBB!.y).toBeLessThan(headlineBB!.y);
  expect(headlineBB!.y).toBeLessThan(highlightsBB!.y);

  const screenshotPath = testInfo.outputPath("ac2-mobile-stack.png");
  await page.screenshot({ path: screenshotPath, fullPage: false });
});

test("AC3 no-weather: HeadlineSummary+HighlightsCard in single column, no empty cell", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_NO_WEATHER_HIGHLIGHTS}`);
  await expect(page.getByTestId("analysis-sidebar")).toHaveAttribute(
    "data-job-status",
    "done",
    { timeout: 20_000 },
  );

  await expect(page.getByTestId("headline-summary-chrome")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("highlights-card")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("weather-report")).not.toBeVisible();

  const leadIn = page.getByTestId("headline-lead-in");
  const leadInClass = await leadIn.getAttribute("class") ?? "";
  expect(leadInClass).not.toMatch(/lg:grid-cols-\[fit-content/);

  const screenshotPath = testInfo.outputPath("ac3-no-weather-single-col.png");
  await page.screenshot({ path: screenshotPath, fullPage: false });
});

test("AC4 empty highlights: right column collapses to HeadlineSummary only", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_WEATHER_NO_HIGHLIGHTS}`);
  await expect(page.getByTestId("analysis-sidebar")).toHaveAttribute(
    "data-job-status",
    "done",
    { timeout: 20_000 },
  );

  await expect(page.getByTestId("headline-summary-chrome")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("weather-report")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("highlights-card")).not.toBeVisible();

  const screenshotPath = testInfo.outputPath("ac4-empty-highlights-no-card.png");
  await page.screenshot({ path: screenshotPath, fullPage: false });
});
