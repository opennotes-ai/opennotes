import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

const JOB_ID = "11111111-1111-7111-8111-111111111111";
const ATTEMPT_ID = "22222222-2222-7222-8222-222222222222";
const SOURCE_URL = "https://quizlet.com/blog/groups-are-now-classes/";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let pollCount = 0;

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

async function readServerPostTimes(page: Page): Promise<number[]> {
  return page.evaluate(() => {
    const win = window as Window & { __vibecheckServerPosts?: number[] };
    return win.__vibecheckServerPosts ?? [];
  });
}

function completedJobState() {
  const sections = Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionData(slug),
        finished_at: "2026-04-23T22:09:00Z",
      },
    ]),
  );
  return {
    job_id: JOB_ID,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections,
    sidebar_payload: null,
    cached: true,
    next_poll_ms: 1500,
    page_title: "Groups are now classes",
    page_kind: "article",
    utterance_count: 3,
  };
}

function sectionData(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") {
    return { harmful_content_matches: [] };
  }
  if (slug === "safety__web_risk") {
    return { findings: [] };
  }
  if (slug === "safety__image_moderation") {
    return { matches: [] };
  }
  if (slug === "safety__video_moderation") {
    return { matches: [] };
  }
  if (slug === "tone_dynamics__flashpoint") {
    return { flashpoint_matches: [] };
  }
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "The discussion stays informational and stable.",
        summary: "Stable informational tone.",
        tone_labels: ["informational"],
        per_speaker_notes: {},
        speaker_arcs: [],
        insufficient_conversation: true,
      },
    };
  }
  if (slug === "facts_claims__dedup") {
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

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${JOB_ID}`
    ) {
      pollCount += 1;
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(completedJobState()));
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
  if (webProcess && !webProcess.killed) {
    webProcess.kill("SIGTERM");
  }
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test("completed analyze URL polls immediately and stays populated after refresh", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const win = window as Window & { __vibecheckServerPosts?: number[] };
    win.__vibecheckServerPosts = [];
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : String(input);
      const method =
        input instanceof Request ? input.method : (init?.method ?? "GET");
      if (method.toUpperCase() === "POST" && url.includes("/_server")) {
        win.__vibecheckServerPosts?.push(performance.now());
      }
      return originalFetch(input, init);
    };
  });

  const initialServerRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" && request.url().includes("/_server"),
    { timeout: 5_000 },
  );

  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`);
  await initialServerRequest;
  const initialServerPostTimes = await readServerPostTimes(page);
  expect(initialServerPostTimes[0]).toBeLessThan(1000);

  for (const slug of ALL_SECTION_SLUGS) {
    await expect(page.locator(`[data-testid="slot-${slug}"]`)).toHaveAttribute(
      "data-slot-state",
      "done",
      { timeout: 10_000 },
    );
  }
  await expect(page.locator('[data-testid="analyze-status"]')).toHaveCount(0);
  expect(pollCount).toBeGreaterThan(0);

  const beforeRefreshPollCount = pollCount;
  const refreshServerRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" && request.url().includes("/_server"),
    { timeout: 5_000 },
  );
  await page.reload();
  await refreshServerRequest;
  const refreshServerPostTimes = await readServerPostTimes(page);
  expect(refreshServerPostTimes[0]).toBeLessThan(1000);

  for (const slug of ALL_SECTION_SLUGS) {
    await expect(page.locator(`[data-testid="slot-${slug}"]`)).toHaveAttribute(
      "data-slot-state",
      "done",
      { timeout: 10_000 },
    );
  }
  await expect(page.locator("text=Preparing analysis")).toHaveCount(0);
  expect(pollCount).toBeGreaterThan(beforeRefreshPollCount);
});
