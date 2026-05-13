import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

const PREPOPULATED_JOB_A = "12121212-1212-7121-8121-121212121212";
const PREPOPULATED_JOB_B = "34343434-3434-7343-8343-343434343434";
const LIVE_JOB_ID = "56565656-5656-7565-8565-565656565656";
const ATTEMPT_ID = "78787878-7878-7787-8787-787878787878";
const SOURCE_URL = "https://quizlet.com/blog/groups-are-now-classes/";
const SECTION_BODY_TEST_IDS = [
  "section-group-body-safety",
  "section-group-body-tone-dynamics",
  "section-group-body-facts-claims",
  "section-group-body-opinions-sentiments",
] as const;

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let livePollCount = 0;

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

function sectionData(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") return { harmful_content_matches: [] };
  if (slug === "safety__web_risk") return { findings: [] };
  if (slug === "safety__image_moderation") return { matches: [] };
  if (slug === "safety__video_moderation") return { matches: [] };
  if (slug === "tone_dynamics__flashpoint") return { flashpoint_matches: [] };
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "The conversation stays stable and informational.",
        summary: "Stable informational tone.",
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
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
      },
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
        data: sectionData(slug),
        finished_at: "2026-05-13T00:40:00Z",
      },
    ]),
  );
}

function sidebarPayload(jobId: string): Record<string, unknown> {
  return {
    source_url: SOURCE_URL,
    page_title: `Prepopulated analysis ${jobId.slice(0, 2)}`,
    page_kind: "article",
    scraped_at: "2026-05-13T00:38:00Z",
    cached: true,
    headline: {
      text: `Headline summary for job ${jobId.slice(0, 2)}.`,
      kind: "synthesized",
      source: "server",
      unavailable_inputs: [],
    },
    weather_report: {
      safety: { level: "safe", confidence: 0.91, rationale: "No harm found." },
      truth: { label: "first_person", logprob: null, alternatives: [] },
      relevance: { label: "on_topic", logprob: null, alternatives: [] },
      sentiment: { label: "neutral", logprob: null, alternatives: [] },
    },
    safety: { harmful_content_matches: [], recommendation: null },
    tone_dynamics: {
      scd: {
        narrative: "The conversation stays stable and informational.",
        summary: "Stable informational tone.",
        tone_labels: ["informational"],
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

function doneState(jobId: string): Record<string, unknown> {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-05-13T00:38:00Z",
    updated_at: "2026-05-13T00:40:00Z",
    sections: allDoneSections(),
    sidebar_payload: sidebarPayload(jobId),
    sidebar_payload_complete: true,
    activity_label: null,
    activity_at: null,
    cached: true,
    next_poll_ms: 1500,
    page_title: `Prepopulated analysis ${jobId.slice(0, 2)}`,
    page_kind: "article",
    utterance_count: 3,
  };
}

function pendingState(): Record<string, unknown> {
  return {
    job_id: LIVE_JOB_ID,
    url: SOURCE_URL,
    status: "analyzing",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-05-13T00:38:00Z",
    updated_at: "2026-05-13T00:39:00Z",
    sections: {},
    sidebar_payload: null,
    sidebar_payload_complete: false,
    activity_label: "Analyzing page",
    activity_at: "2026-05-13T00:39:00Z",
    cached: false,
    next_poll_ms: 250,
    page_title: null,
    page_kind: null,
    utterance_count: 0,
  };
}

function liveState(): Record<string, unknown> {
  livePollCount += 1;
  if (livePollCount <= 2) return pendingState();
  return doneState(LIVE_JOB_ID);
}

async function expectTopLevelGroupsCollapsed(page: Page): Promise<void> {
  for (const testId of SECTION_BODY_TEST_IDS) {
    await expect(page.locator(`[data-testid="${testId}"]`)).toBeHidden();
  }
}

async function expectTopLevelGroupsExpanded(page: Page): Promise<void> {
  for (const testId of SECTION_BODY_TEST_IDS) {
    await expect(page.locator(`[data-testid="${testId}"]`)).toBeVisible();
  }
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${PREPOPULATED_JOB_A}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(doneState(PREPOPULATED_JOB_A)));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${PREPOPULATED_JOB_B}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(doneState(PREPOPULATED_JOB_B)));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${LIVE_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(liveState()));
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
  livePollCount = 0;
});

test("prepopulated analyze job loads top-level sidebar groups collapsed", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${PREPOPULATED_JOB_A}`);

  await expect(page.locator('[data-testid="headline-summary"]')).toBeVisible();
  await expect(page.locator('[data-testid="weather-report"]')).toBeVisible();
  await expectTopLevelGroupsCollapsed(page);
});

test("live job collapses top-level sidebar groups when headline and weather arrive", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${LIVE_JOB_ID}`);

  await expect(page.locator('[data-testid="analysis-sidebar"]')).toHaveAttribute(
    "data-job-status",
    "analyzing",
  );
  await expectTopLevelGroupsExpanded(page);
  await expect(page.locator('[data-testid="headline-summary"]')).toBeVisible();
  await expect(page.locator('[data-testid="weather-report"]')).toBeVisible();
  await expectTopLevelGroupsCollapsed(page);
});

test("client-side navigation between prepopulated jobs keeps sidebar groups collapsed", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${PREPOPULATED_JOB_A}`);

  await expect(page.locator('[data-testid="headline-summary"]')).toBeVisible();
  await expectTopLevelGroupsCollapsed(page);

  await page.locator('[data-testid="section-toggle-Safety"]').click();
  await expect(
    page.locator('[data-testid="section-group-body-safety"]'),
  ).toBeVisible();

  await page.evaluate((jobId) => {
    const link = document.createElement("a");
    link.href = `/analyze?job=${jobId}`;
    link.dataset.testid = "navigate-job-b";
    link.textContent = "Navigate to job B";
    document.body.append(link);
  }, PREPOPULATED_JOB_B);
  await page.locator('[data-testid="navigate-job-b"]').click();

  await expect(page).toHaveURL(new RegExp(`job=${PREPOPULATED_JOB_B}`));
  await expect(
    page.locator('[data-testid="headline-summary-text"]'),
  ).toContainText("job 34");
  await expectTopLevelGroupsCollapsed(page);
});
