import { expect, test, type Locator, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { createServer, type Server } from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";
import { ALL_SECTION_SLUGS, waitForAllSectionsTerminal } from "./fixtures/quizlet";

const TIMESTAMPED_JOB_ID = "77777777-7777-7777-8777-777777777777";
const UNTIMESTAMPED_JOB_ID = "88888888-8888-7888-8888-888888888888";
const ATTEMPT_ID = "99999999-9999-7999-8999-999999999999";
const SOURCE_URL = "https://example.com/sentiment-timeline-fixture";
const BASE_MS = Date.UTC(2026, 0, 1, 12, 0, 0);

type SentimentLabel = "positive" | "negative" | "neutral";

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

function makeAnchor(
  utteranceId: string,
  position: number,
  offsetMinutes: number,
  withTimestamp: boolean,
) {
  return {
    position,
    utterance_id: utteranceId,
    timestamp: withTimestamp
      ? new Date(BASE_MS + offsetMinutes * 60_000).toISOString()
      : null,
  };
}

function buildUtterances(withTimestamps: boolean) {
  const utterances = [
    { id: "utt-01", offsetMinutes: 0 },
    { id: "utt-02", offsetMinutes: 20 },
    { id: "utt-03", offsetMinutes: 40 },
    { id: "utt-04", offsetMinutes: 60 },
    { id: "utt-05", offsetMinutes: 80 },
    { id: "utt-06", offsetMinutes: 100 },
    { id: "utt-07", offsetMinutes: 140 },
    { id: "utt-08", offsetMinutes: 180 },
    { id: "utt-09", offsetMinutes: 200 },
    { id: "utt-10", offsetMinutes: 220 },
    { id: "utt-11", offsetMinutes: 235 },
    { id: "utt-12", offsetMinutes: 240 },
  ];

  return utterances.map((entry, index) =>
    makeAnchor(entry.id, index + 1, entry.offsetMinutes, withTimestamps)
  );
}

function makeScore(utteranceId: string, label: SentimentLabel, valence: number) {
  return {
    utterance_id: utteranceId,
    label,
    valence,
  };
}

function sentimentStats() {
  return {
    positive_pct: 42,
    negative_pct: 33,
    neutral_pct: 25,
    mean_valence: 0.12,
    per_utterance: [
      makeScore("utt-01", "positive", 0.86),
      makeScore("utt-02", "negative", -0.74),
      makeScore("utt-03", "neutral", 0),
      makeScore("utt-04", "positive", 0.62),
      makeScore("utt-05", "positive", 0.71),
      makeScore("utt-06", "negative", -0.68),
      makeScore("utt-07", "neutral", 0),
      makeScore("utt-08", "negative", -0.52),
      makeScore("utt-09", "positive", 0.78),
      makeScore("utt-10", "neutral", 0),
      makeScore("utt-11", "positive", 0.67),
      makeScore("utt-12", "negative", -0.81),
    ],
  };
}

function sectionDataFor(slug: string) {
  if (slug === "safety__moderation") {
    return { harmful_content_matches: [] };
  }
  if (slug === "safety__web_risk") return { findings: [] };
  if (slug === "safety__image_moderation") return { matches: [] };
  if (slug === "safety__video_moderation") return { matches: [] };
  if (slug === "tone_dynamics__flashpoint") return { flashpoint_matches: [] };
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "Discussion remains mostly steady.",
        summary: "Steady conversation.",
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
    return { sentiment_stats: sentimentStats() };
  }
  return { subjective_claims: [] };
}

function allDoneSections() {
  return Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionDataFor(slug),
        finished_at: "2026-05-06T19:00:00Z",
      },
    ]),
  );
}

function sidebarPayload(withTimestamps: boolean) {
  return {
    headline: null,
    utterances: buildUtterances(withTimestamps),
    safety: {
      recommendation: null,
      harmful_content_matches: [],
    },
    web_risk: { findings: [] },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      flashpoint_matches: [],
      scd: sectionDataFor("tone_dynamics__scd").scd,
    },
    facts_claims: {
      claims_report: sectionDataFor("facts_claims__dedup").claims_report,
      known_misinformation: [],
    },
    opinions_sentiments: {
      opinions_report: {
        sentiment_stats: sentimentStats(),
        subjective_claims: [],
      },
    },
    cached_at: "2026-05-06T19:00:00Z",
  };
}

function terminalJobState(jobId: string, withTimestamps: boolean) {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-06T18:59:00Z",
    updated_at: "2026-05-06T19:00:00Z",
    sections: allDoneSections(),
    sidebar_payload: sidebarPayload(withTimestamps),
    sidebar_payload_complete: true,
    cached: true,
    next_poll_ms: 1500,
    page_title: "Sentiment timeline fixture",
    page_kind: "article",
    utterance_count: 12,
  };
}

async function gotoAnalyze(page: Page, jobId: string) {
  await page.goto(`${webBaseUrl}/analyze?job=${jobId}`);
  await expect(page.getByTestId("analyze-layout")).toBeVisible();
  await waitForAllSectionsTerminal(page, { timeoutMs: 30_000 });
}

async function expectCanvasToRender(locator: Locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, "chart canvas should have a measurable bounding box").not.toBeNull();
  expect(box!.width, "chart canvas should render with non-zero width").toBeGreaterThan(0);
  expect(box!.height, "chart canvas should render with non-zero height").toBeGreaterThan(0);
}

async function expectChartsAlignedWithinTwoPixels(page: Page) {
  const measurement = await page.evaluate(() => {
    const rolling = document.querySelector(
      '[data-testid="sentiment-rolling-chart"]',
    ) as HTMLElement | null;
    const punch = document.querySelector(
      '[data-testid="sentiment-punch-card-chart"]',
    ) as HTMLElement | null;
    if (!rolling || !punch) {
      throw new Error("sentiment timeline chart wrappers are missing");
    }

    const rollingBox = rolling.getBoundingClientRect();
    const punchBox = punch.getBoundingClientRect();
    return {
      xDiff: Math.abs(rollingBox.x - punchBox.x),
      widthDiff: Math.abs(rollingBox.width - punchBox.width),
      rightDiff: Math.abs(rollingBox.right - punchBox.right),
    };
  });

  expect(measurement.xDiff, "chart wrappers should share the same left edge").toBeLessThanOrEqual(2);
  expect(measurement.widthDiff, "chart wrappers should share the same width").toBeLessThanOrEqual(2);
  expect(measurement.rightDiff, "chart wrappers should share the same right edge").toBeLessThanOrEqual(2);
}

async function hoverUntilPunchCardTooltipAppears(
  page: Page,
  canvas: Locator,
): Promise<void> {
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  if (!box) {
    throw new Error("punch-card canvas bounding box is unavailable");
  }

  const leftPadding = 64;
  const rightPadding = 8;
  const topPadding = 8;
  const bottomPadding = 24;
  const bucketCount = 8;
  const rowCount = 3;
  const plotWidth = Math.max(1, box.width - leftPadding - rightPadding);
  const plotHeight = Math.max(1, box.height - topPadding - bottomPadding);

  for (let bucketIndex = 0; bucketIndex < bucketCount; bucketIndex += 1) {
    for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
      const x =
        box.x + leftPadding + plotWidth * ((bucketIndex + 0.5) / bucketCount);
      const y =
        box.y + topPadding + plotHeight * ((rowIndex + 0.5) / rowCount);
      await page.mouse.move(
        x,
        y,
      );
      await page.waitForTimeout(100);

      const tooltipVisible = await page.evaluate(() =>
        /Positive:\s*\d|Neutral:\s*\d|Negative:\s*\d/.test(
          document.body.textContent ?? "",
        )
      );
      if (tooltipVisible) {
        return;
      }
    }
  }

  throw new Error("did not find a hover point that exposed a punch-card tooltip");
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");

    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${TIMESTAMPED_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(terminalJobState(TIMESTAMPED_JOB_ID, true)));
      return;
    }

    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${UNTIMESTAMPED_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(terminalJobState(UNTIMESTAMPED_JOB_ID, false)));
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

    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/screenshot"
    ) {
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
  if (webProcess) {
    await stopWebProcess(webProcess);
  }
  await new Promise<void>((resolve) => apiServer.close(() => resolve()));
});

test("shows the sentiment timeline for timestamped utterances and keeps chart widths aligned", async ({
  page,
}) => {
  await gotoAnalyze(page, TIMESTAMPED_JOB_ID);

  const timeline = page.getByTestId("sentiment-timeline");
  await expect(timeline).toBeVisible();
  await expect(page.getByTestId("sentiment-mean-valence")).toHaveCount(0);

  const rollingChart = page.getByTestId("sentiment-rolling-chart");
  const punchCardChart = page.getByTestId("sentiment-punch-card-chart");
  const rollingCanvas = rollingChart.locator("canvas");
  const punchCanvas = punchCardChart.locator("canvas");

  await expect(rollingCanvas).toHaveCount(1);
  await expect(punchCanvas).toHaveCount(1);
  await expectCanvasToRender(rollingCanvas.first());
  await expectCanvasToRender(punchCanvas.first());
  await expectChartsAlignedWithinTwoPixels(page);
  await hoverUntilPunchCardTooltipAppears(page, punchCanvas.first());
});

test("hides the timeline when timestamps are absent and keeps the percentage bar visible", async ({
  page,
}) => {
  await gotoAnalyze(page, UNTIMESTAMPED_JOB_ID);

  await expect(page.getByTestId("sentiment-timeline")).toHaveCount(0);
  await expect(page.getByTestId("report-opinions_sentiments__sentiment")).toBeVisible();
  await expect(page.getByTestId("sentiment-mean-valence")).toHaveCount(0);
});
