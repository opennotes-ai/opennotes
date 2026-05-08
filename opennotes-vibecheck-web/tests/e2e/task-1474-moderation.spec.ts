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

const SAFE_JOB_ID = "33333333-3333-7333-8333-333333333333";
const UNSAFE_JOB_ID = "44444444-4444-7444-8444-444444444444";
const ATTEMPT_ID = "55555555-5555-7555-8555-555555555555";
const SAFE_URL = "https://example.test/safe-video-and-image-fixture";
const UNSAFE_URL = "https://malware.test/blocked";
const VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
const ADULT_IMAGE_URL = "https://fixtures.example/adult-safe-search.jpg";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let safePollCount = 0;

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
  switch (slug) {
    case "safety__moderation":
      return {
        harmful_content_matches: [
          {
            utterance_id: "u1",
            utterance_text: "The page contains a policy-sensitive claim.",
            max_score: 0.91,
            categories: { harassment: true },
            scores: { harassment: 0.91 },
            flagged_categories: ["harassment"],
            source: "openai",
          },
          {
            utterance_id: "u2",
            utterance_text: "Natural Language also flagged this passage.",
            max_score: 0.84,
            categories: { toxic: true },
            scores: { toxic: 0.84 },
            flagged_categories: ["toxic"],
            source: "gcp",
          },
        ],
      };
    case "safety__web_risk":
      return { findings: [] };
    case "safety__image_moderation":
      return {
        matches: [
          {
            utterance_id: "u3",
            image_url: ADULT_IMAGE_URL,
            adult: 0.96,
            violence: 0.08,
            racy: 0.82,
            medical: 0.04,
            spoof: 0.01,
            flagged: true,
            max_likelihood: 0.96,
          },
        ],
      };
    case "safety__video_moderation":
      return {
        matches: [
          {
            utterance_id: "u4",
            video_url: VIDEO_URL,
            segment_findings: [
              {
                start_offset_ms: 4200,
                end_offset_ms: 4200,
                adult: 0.09,
                violence: 0.88,
                racy: 0.12,
                medical: 0.03,
                spoof: 0.02,
                flagged: true,
                max_likelihood: 0.88,
              },
            ],
            flagged: true,
            max_likelihood: 0.88,
          },
        ],
      };
    case "tone_dynamics__flashpoint":
      return { flashpoint_matches: [] };
    case "tone_dynamics__scd":
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
    case "facts_claims__dedup":
    case "facts_claims__evidence":
    case "facts_claims__premises":
      return {
        claims_report: {
          deduped_claims: [],
          total_claims: 0,
          total_unique: 0,
        },
      };
    case "facts_claims__known_misinfo":
      return { known_misinformation: [] };
    case "opinions_sentiments__sentiment":
      return {
        sentiment_stats: {
          per_utterance: [],
          positive_pct: 0,
          negative_pct: 0,
          neutral_pct: 100,
          mean_valence: 0,
        },
      };
    default:
      return { subjective_claims: [] };
  }
}

function sectionsFor(state: "running" | "done") {
  return Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state,
        attempt_id: ATTEMPT_ID,
        data: state === "done" ? sectionData(slug) : null,
        started_at: "2026-04-23T22:10:00Z",
        finished_at: state === "done" ? "2026-04-23T22:10:12Z" : null,
      },
    ]),
  );
}

function safeJobState() {
  safePollCount += 1;
  const done = safePollCount >= 2;
  return {
    job_id: SAFE_JOB_ID,
    url: SAFE_URL,
    status: done ? "done" : "analyzing",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-23T22:10:00Z",
    updated_at: "2026-04-23T22:10:12Z",
    sections: sectionsFor(done ? "done" : "running"),
    sidebar_payload: null,
    cached: false,
    next_poll_ms: 500,
    page_title: "Moderation fixture",
    page_kind: "article",
    utterance_count: 4,
  };
}

function unsafeJobState() {
  return {
    job_id: UNSAFE_JOB_ID,
    url: UNSAFE_URL,
    status: "failed",
    attempt_id: ATTEMPT_ID,
    error_code: "unsafe_url",
    error_message: "Web Risk flagged this URL before analysis.",
    created_at: "2026-04-23T22:11:00Z",
    updated_at: "2026-04-23T22:11:01Z",
    sections: {},
    sidebar_payload: {
      source_url: UNSAFE_URL,
      page_title: null,
      page_kind: "other",
      scraped_at: "2026-04-23T22:11:01Z",
      cached: false,
      safety: { harmful_content_matches: [] },
      tone_dynamics: { flashpoint_matches: [], scd: sectionData("tone_dynamics__scd").scd },
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
      web_risk: {
        findings: [
          {
            url: UNSAFE_URL,
            threat_types: ["MALWARE", "SOCIAL_ENGINEERING"],
          },
        ],
      },
      image_moderation: { matches: [] },
      video_moderation: { matches: [] },
    },
    cached: false,
    next_poll_ms: 1500,
    page_title: null,
    page_kind: "other",
    utterance_count: 0,
  };
}

async function submitUrl(
  page: Page,
  url: string,
): Promise<{ jobId: string | null; pendingError: string | null }> {
  await page.goto(webBaseUrl);
  await page.locator("#vibecheck-url").fill(url);
  await Promise.all([
    page.waitForURL((u) => u.pathname === "/analyze", { timeout: 30_000 }),
    page.locator('button[type="submit"]').click(),
  ]);
  const parsed = new URL(page.url());
  return {
    jobId: parsed.searchParams.get("job"),
    pendingError: parsed.searchParams.get("pending_error"),
  };
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    void (async () => {
      const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
      if (request.method === "POST" && requestUrl.pathname === "/api/analyze") {
        const body = (await readJsonBody(request)) as { url?: string };
        const isUnsafe = body.url === UNSAFE_URL;
        writeJson(response, 202, {
          job_id: isUnsafe ? UNSAFE_JOB_ID : SAFE_JOB_ID,
          status: isUnsafe ? "failed" : "pending",
          cached: false,
        });
        return;
      }
      if (
        request.method === "GET" &&
        requestUrl.pathname === `/api/analyze/${SAFE_JOB_ID}`
      ) {
        writeJson(response, 200, safeJobState());
        return;
      }
      if (
        request.method === "GET" &&
        requestUrl.pathname === `/api/analyze/${UNSAFE_JOB_ID}`
      ) {
        writeJson(response, 200, unsafeJobState());
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

test("1474 moderation sections fill progressively and render provider/source details", async ({
  page,
}) => {
  test.setTimeout(75_000);
  safePollCount = 0;

  const { jobId, pendingError } = await submitUrl(page, SAFE_URL);
  expect(pendingError).toBeNull();
  expect(jobId).toBe(SAFE_JOB_ID);

  for (const slug of ALL_SECTION_SLUGS) {
    await expect(page.locator(`[data-testid="slot-${slug}"]`)).toHaveAttribute(
      "data-slot-state",
      "done",
      { timeout: 30_000 },
    );
  }

  await expect(
    page.locator('[data-testid="safety-provider-label"]'),
  ).toContainText(["OpenAI Moderation", "Google Natural Language Moderation"]);
  await expect(
    page.locator('[data-testid="slot-safety__video_moderation"]'),
  ).toHaveAttribute("data-slot-state", "done", { timeout: 60_000 });
  await expect(
    page.locator('[data-testid="report-safety__video_moderation"]'),
  ).toContainText(VIDEO_URL);
  await expect(
    page.locator('[data-testid="video-frame-flag"]'),
  ).toContainText("flagged");
  await expect(
    page.locator('[data-testid="video-frame-category"]'),
  ).toContainText("violence");

  await expect(
    page.locator('[data-testid="image-moderation-match"]'),
  ).toHaveAttribute("data-flagged", "true");
  await expect(
    page.locator('[data-testid="image-moderation-max"]'),
  ).toHaveCount(0);
  await expect(
    page.locator('[data-testid="image-moderation-category"]'),
  ).toContainText(["adult", "racy"]);
});

test("1474 unsafe URL renders terminal failure with Web Risk threats only", async ({
  page,
}) => {
  const { jobId, pendingError } = await submitUrl(page, UNSAFE_URL);
  expect(pendingError).toBeNull();
  expect(jobId).toBe(UNSAFE_JOB_ID);

  await expect(page.locator('[data-testid="job-failure-card"]')).toHaveAttribute(
    "data-error-code",
    "unsafe_url",
    { timeout: 30_000 },
  );
  await expect(page.locator('[data-testid="job-failure-card"]')).toContainText(
    "Web Risk flagged this URL before analysis.",
  );
  await expect(
    page.locator('[data-testid="unsafe-url-threat"]'),
  ).toContainText(["malware", "social engineering"]);
  await expect(page.locator('[data-testid="analysis-sidebar"]')).toHaveCount(0);
  await expect(page.locator('[data-testid^="slot-"]')).toHaveCount(0);
});
