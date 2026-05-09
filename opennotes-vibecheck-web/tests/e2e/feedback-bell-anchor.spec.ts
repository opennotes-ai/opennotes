import { test, expect } from "@playwright/test";
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
import { stopWebProcess } from "./_helpers/web-process";

const JOB_ID = "bb000000-0000-7000-8000-000000000001";
const ATTEMPT_ID = "cc000000-0000-7000-8000-000000000001";
const SOURCE_URL = "https://example.test/bell-anchor-fixture";

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

function writeJson(
  response: ServerResponse<IncomingMessage>,
  status: number,
  body: unknown,
): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
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
        narrative: "",
        summary: "",
        tone_labels: [],
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
  if (slug === "facts_claims__known_misinfo") return { known_misinformation: [] };
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

function jobState() {
  const sections = Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionData(slug),
        finished_at: "2026-05-01T12:00:00Z",
      },
    ]),
  );

  return {
    job_id: JOB_ID,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-01T12:00:00Z",
    updated_at: "2026-05-01T12:00:00Z",
    sections,
    sidebar_payload: {
      cached_at: "2026-05-01T12:00:00Z",
      headline: null,
      safety: {
        harmful_content_matches: [],
        recommendation: {
          level: "safe",
          rationale: "No signals.",
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
    },
    sidebar_payload_complete: true,
    cached: true,
    next_poll_ms: 1500,
    page_title: "Bell anchor fixture",
    page_kind: "article",
    utterance_count: 1,
  };
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");

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
  if (webProcess) await stopWebProcess(webProcess);
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test("FeedbackBell sits in bottom-right corner of short-content SafetyRecommendationReport", async ({
  page,
}) => {
  test.setTimeout(90_000);

  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`, {
    waitUntil: "networkidle",
  });

  await expect(page.locator('[data-testid="analyze-layout"]')).toBeVisible({
    timeout: 30_000,
  });

  const report = page.getByTestId("safety-recommendation-report");

  if (!(await report.isVisible())) {
    const toggle = page.getByTestId("section-toggle-Safety");
    if (await toggle.isVisible()) {
      await toggle.click();
    }
  }
  await expect(report).toBeVisible({ timeout: 30_000 });

  const bell = page.getByRole("button", {
    name: /Send feedback about card:safety-recommendation/,
  });
  await expect(bell).toBeVisible({ timeout: 10_000 });

  const { bellBox, reportBox } = await page.evaluate(() => {
    const reportEl = document.querySelector(
      '[data-testid="safety-recommendation-report"]',
    ) as HTMLElement | null;
    const bellEl = document.querySelector(
      '[aria-label*="card:safety-recommendation"]',
    ) as HTMLElement | null;
    if (!reportEl || !bellEl) {
      throw new Error(
        `Could not find elements: report=${Boolean(reportEl)}, bell=${Boolean(bellEl)}`,
      );
    }
    return {
      reportBox: reportEl.getBoundingClientRect().toJSON(),
      bellBox: bellEl.getBoundingClientRect().toJSON(),
    };
  });

  const bellRight = bellBox.right;
  const reportRight = reportBox.right;
  const bellBottom = bellBox.bottom;
  const reportBottom = reportBox.bottom;

  expect(
    reportRight - bellRight,
    `bell right edge should be within 20px of report right edge (gap: ${reportRight - bellRight}px)`,
  ).toBeLessThan(20);

  expect(
    reportBottom - bellBottom,
    `bell bottom edge should be within 20px of report bottom edge (gap: ${reportBottom - bellBottom}px)`,
  ).toBeLessThan(20);

  expect(
    bellRight,
    "bell must not overflow report right edge",
  ).toBeLessThanOrEqual(reportRight + 1);

  expect(
    bellBottom,
    "bell must not overflow report bottom edge",
  ).toBeLessThanOrEqual(reportBottom + 1);
});
