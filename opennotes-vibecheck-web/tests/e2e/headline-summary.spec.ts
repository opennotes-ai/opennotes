import { test, expect, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { createServer, type Server } from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

const SERVER_HEADLINE_JOB_ID = "11111111-1111-7111-8111-111111111111";
const FALLBACK_HEADLINE_JOB_ID = "33333333-3333-7333-8333-333333333333";
const ATTEMPT_ID = "22222222-2222-7222-8222-222222222222";
const SOURCE_URL = "https://WWW.www.Example.COM/news/story-title.html";
const SERVER_HEADLINE_TEXT = "Server headline lands from the terminal payload.";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));

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

function sidebarPayload(headline: Record<string, unknown> | null) {
  return {
    cached_at: "2026-04-23T22:09:00Z",
    headline,
    safety: {
      harmful_content_matches: [],
      recommendation: {
        level: "safe",
        rationale: "No safety concerns are present in the mocked payload.",
        top_signals: [],
        unavailable_inputs: [],
      },
    },
    web_risk: { findings: [] },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      flashpoint_matches: [],
      scd: sectionData("tone_dynamics__scd").scd,
    },
    facts_claims: {
      claims_report: sectionData("facts_claims__dedup").claims_report,
      known_misinformation: [],
    },
    opinions_sentiments: {
      opinions_report: {
        sentiment_stats:
          sectionData("opinions_sentiments__sentiment").sentiment_stats,
        subjective_claims: [],
      },
    },
  };
}

function terminalJobState(jobId: string) {
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
  const headline =
    jobId === SERVER_HEADLINE_JOB_ID
      ? { text: SERVER_HEADLINE_TEXT, kind: "synthesized" }
      : null;
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections,
    sidebar_payload: sidebarPayload(headline),
    cached: true,
    next_poll_ms: 1500,
    page_title: jobId === FALLBACK_HEADLINE_JOB_ID ? "" : "Groups are now classes",
    page_kind: "article",
    utterance_count: 3,
  };
}

async function assertHeadlinePrecedesSafety(page: Page): Promise<void> {
  const headlinePrecedesSafety = await page.evaluate(() => {
    const h = document.querySelector('[data-testid="headline-summary"]');
    const s = document.querySelector(
      '[data-testid="safety-recommendation-report"]',
    );
    if (!h || !s) {
      throw new Error(
        `Cannot compare headline/safety order: headline-summary=${Boolean(
          h,
        )}, safety-recommendation-report=${Boolean(s)}`,
      );
    }
    return Boolean(
      h.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(
    headlinePrecedesSafety,
    "headline-summary must appear above safety-recommendation-report in the sidebar",
  ).toBe(true);
}

async function assertHeadlineSummary(
  page: Page,
  source: "server" | "fallback",
): Promise<string> {
  await expect(page.locator('[data-testid="analyze-layout"]')).toBeVisible({
    timeout: 30_000,
  });
  const finalStates = await waitForAllSectionsTerminal(page, {
    timeoutMs: 30_000,
  });
  const doneCount = ALL_SECTION_SLUGS.filter(
    (slug) => finalStates[slug] === "done",
  ).length;
  expect(
    doneCount,
    `All sections must reach 'done' before the headline assertion (got ${doneCount}: ${JSON.stringify(finalStates)})`,
  ).toBe(ALL_SECTION_SLUGS.length);

  const headline = page.getByTestId("headline-summary");
  await expect(headline, "headline summation block must render").toBeVisible({
    timeout: 30_000,
  });

  const text = page.getByTestId("headline-summary-text");
  const headlineText = (await text.textContent())?.trim() ?? "";
  expect(
    headlineText.length,
    `headline-summary-text must be non-empty (got: ${JSON.stringify(headlineText)})`,
  ).toBeGreaterThan(0);

  const kind = await headline.getAttribute("data-headline-kind");
  expect(
    kind,
    `data-headline-kind must be 'stock' or 'synthesized' (got: ${JSON.stringify(kind)})`,
  ).toMatch(/^(stock|synthesized)$/);

  await expect(headline).toHaveAttribute("data-headline-source", source);
  await expect(
    text,
    "headline text must not render the read-more truncation chrome",
  ).not.toHaveAttribute("data-truncated", /.*/);

  const safetyRec = page.getByTestId("safety-recommendation-report");
  await expect(
    safetyRec,
    "safety-recommendation-report must render alongside the headline so we can verify ordering",
  ).toBeVisible({ timeout: 10_000 });
  await assertHeadlinePrecedesSafety(page);
  return headlineText;
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    const jobId = requestUrl.pathname.split("/").pop() ?? "";
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${jobId}` &&
      (jobId === SERVER_HEADLINE_JOB_ID || jobId === FALLBACK_HEADLINE_JOB_ID)
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(terminalJobState(jobId)));
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
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test("mocked terminal poll payload renders server headline source", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${SERVER_HEADLINE_JOB_ID}`);
  const headlineText = await assertHeadlineSummary(page, "server");
  expect(headlineText).toBe(SERVER_HEADLINE_TEXT);
});

test("mocked terminal poll payload without headline renders fallback source", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${FALLBACK_HEADLINE_JOB_ID}`);
  const headlineText = await assertHeadlineSummary(page, "fallback");
  expect(headlineText).toBe("example.com — story title — appears clean");
});

test("live upstream headline summary renders above safety-recommendation", async ({
  page,
}) => {
  test.skip(
    process.env.VIBECHECK_E2E_LIVE_UPSTREAM !== "1",
    "Set VIBECHECK_E2E_LIVE_UPSTREAM=1 to run the live upstream headline check.",
  );
  test.setTimeout(220_000);

  const { jobId, pendingError } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(
    pendingError,
    "Submitting the canonical Quizlet URL must not produce a pending_error redirect",
  ).toBeNull();
  expect(jobId, "AnalyzePage must be reached with ?job=<id>").toBeTruthy();

  await assertHeadlineSummary(page, "server");
});
