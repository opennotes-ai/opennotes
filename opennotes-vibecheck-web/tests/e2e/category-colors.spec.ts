import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

const JOB_ID = "77777777-7777-7777-8777-777777777777";
const ATTEMPT_ID = "88888888-8888-7888-8888-888888888888";
const FIXTURE_URL = "https://example.test/category-color-fixture";

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

async function readJsonBody(request: IncomingMessage): Promise<unknown> {
  let body = "";
  for await (const chunk of request) {
    body += chunk.toString();
  }
  if (!body) return {};
  return JSON.parse(body);
}

function writeJson(
  response: ServerResponse<IncomingMessage>,
  status: number,
  body: unknown,
): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function sectionData(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") {
    return {
      harmful_content_matches: [
        {
          utterance_id: "u1",
          utterance_text: "High confidence violence.",
          max_score: 0.9,
          categories: { violence: true },
          scores: { violence: 0.9 },
          flagged_categories: ["violence"],
          source: "openai",
        },
        {
          utterance_id: "u2",
          utterance_text: "Low confidence sexual category.",
          max_score: 0.3,
          categories: { sexual: true },
          scores: { sexual: 0.3 },
          flagged_categories: ["sexual"],
          source: "openai",
        },
        {
          utterance_id: "u3",
          utterance_text: "Sensitive finance category.",
          max_score: 0.9,
          categories: { Finance: true },
          scores: { Finance: 0.9 },
          flagged_categories: ["Finance"],
          source: "gcp",
        },
        {
          utterance_id: "u4",
          utterance_text: "Unknown future category.",
          max_score: 0.9,
          categories: { Toxic: true },
          scores: { Toxic: 0.9 },
          flagged_categories: ["Toxic"],
          source: "gcp",
        },
      ],
    };
  }
  if (slug === "safety__web_risk") return { findings: [] };
  if (slug === "safety__image_moderation") return { matches: [] };
  if (slug === "safety__video_moderation") return { matches: [] };
  if (slug === "tone_dynamics__flashpoint") return { flashpoint_matches: [] };
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "The exchange remains stable.",
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

function sections() {
  return Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionData(slug),
        started_at: "2026-05-04T22:10:00Z",
        finished_at: "2026-05-04T22:10:12Z",
      },
    ]),
  );
}

function jobState() {
  return {
    job_id: JOB_ID,
    url: FIXTURE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-04T22:10:00Z",
    updated_at: "2026-05-04T22:10:12Z",
    sections: sections(),
    sidebar_payload: null,
    sidebar_payload_complete: true,
    cached: false,
    next_poll_ms: 1000,
    page_title: "Category color fixture",
    page_kind: "article",
    utterance_count: 4,
  };
}

async function submitUrl(page: Page): Promise<string | null> {
  await page.goto(webBaseUrl);
  await page.locator("#vibecheck-url").fill(FIXTURE_URL);
  await Promise.all([
    page.waitForURL((url) => url.pathname === "/analyze", {
      timeout: 30_000,
    }),
    page.getByRole("button", { name: "Analyze", exact: true }).click(),
  ]);
  return new URL(page.url()).searchParams.get("job");
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    void (async () => {
      const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
      if (request.method === "POST" && requestUrl.pathname === "/api/analyze") {
        await readJsonBody(request);
        writeJson(response, 202, {
          job_id: JOB_ID,
          status: "done",
          cached: false,
        });
        return;
      }
      if (
        request.method === "GET" &&
        requestUrl.pathname === `/api/analyze/${JOB_ID}`
      ) {
        writeJson(response, 200, jobState());
        return;
      }
      if (
        request.method === "GET" &&
        requestUrl.pathname === "/api/frame-compat"
      ) {
        writeJson(response, 200, { can_iframe: true, blocking_header: null });
        return;
      }
      if (
        request.method === "GET" &&
        requestUrl.pathname === "/api/screenshot"
      ) {
        writeJson(response, 200, { screenshot_url: null });
        return;
      }
      writeJson(response, 404, { error_code: "not_found" });
    })().catch((error: unknown) => {
      writeJson(response, 500, {
        error_code: "internal",
        message: error instanceof Error ? error.message : String(error),
      });
    });
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

test("moderation labels render harm, sensitive, and default colors", async ({
  page,
}) => {
  const jobId = await submitUrl(page);
  expect(jobId).toBe(JOB_ID);

  await expect(
    page.locator('[data-testid="slot-safety__moderation"]'),
  ).toHaveAttribute("data-slot-state", "done", { timeout: 30_000 });

  await expect(page.locator('[data-testid="safety-category"]')).toHaveCount(4);
  await expect(
    page.getByTestId("safety-category").filter({ hasText: "violence" }),
  ).toHaveAttribute("data-color", "red");
  await expect(
    page.getByTestId("safety-category").filter({ hasText: "sexual" }),
  ).toHaveAttribute("data-color", "yellow");
  await expect(
    page.getByTestId("safety-category").filter({ hasText: "Finance" }),
  ).toHaveAttribute("data-color", "gray");
  await expect(
    page.getByTestId("safety-category").filter({ hasText: "Toxic" }),
  ).toHaveAttribute("data-color", "yellow");

  await expect(
    page.locator('[data-testid="safety-category"][data-color="red"]'),
  ).toHaveText("violence");
  await page.screenshot({
    path: "test-results/category-colors-moderation.png",
    fullPage: true,
  });
});
