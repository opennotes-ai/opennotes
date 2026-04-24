import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

/**
 * AC5 — TASK-1474.22 visual progress feedback during extracting phase.
 *
 * Drives a job through `extracting → analyzing → done` via a mock API
 * server scripted by poll count. Asserts:
 *
 *   1. While status=extracting, the [data-testid="extracting-indicator"]
 *      is visible AND every section slot is in `running` state with a
 *      content-shape skeleton mounted (so the user perceives motion).
 *   2. Once status flips to `analyzing` and the server seeds real slot
 *      states, the indicator disappears but the per-slot skeletons
 *      stay (smooth handoff).
 *   3. Once status reaches `done`, the indicator stays absent.
 *   4. Negative path: a `failed` status shows the JobFailureCard and
 *      the Sidebar (and therefore the indicator) is not rendered.
 *   5. Cached-hit path: when the very first poll returns `done`, the
 *      indicator must NOT flash on screen.
 */

const JOB_ID = "11111111-1111-7111-8111-111111111111";
const FAILED_JOB_ID = "22222222-2222-7222-8222-222222222222";
const CACHED_JOB_ID = "33333333-3333-7333-8333-333333333333";
const ATTEMPT_ID = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
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
  if (slug === "facts_claims__dedup") {
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

interface JobStateOverrides {
  jobId?: string;
  status: "pending" | "extracting" | "analyzing" | "done" | "failed";
  sections?: Record<string, unknown>;
  cached?: boolean;
  errorCode?: string | null;
  errorMessage?: string | null;
}

function jobState(overrides: JobStateOverrides): Record<string, unknown> {
  return {
    job_id: overrides.jobId ?? JOB_ID,
    url: SOURCE_URL,
    status: overrides.status,
    attempt_id: ATTEMPT_ID,
    error_code: overrides.errorCode ?? null,
    error_message: overrides.errorMessage ?? null,
    error_host: null,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections: overrides.sections ?? {},
    sidebar_payload: null,
    cached: overrides.cached ?? false,
    next_poll_ms: 500,
    page_title: null,
    page_kind: null,
    utterance_count: 0,
  };
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

function jobStateForCount(count: number): Record<string, unknown> {
  // Drive a deterministic state machine from the polling cadence so the
  // assertions below can rely on observable, ordered transitions.
  //   poll 1            → extracting (sections: {})
  //   poll 2            → still extracting (gives the test time to read
  //                       the indicator without races)
  //   poll 3            → analyzing (every slot seeded as `running`)
  //   poll 4 and after  → done (every slot done)
  if (count <= 2) {
    return jobState({ status: "extracting" });
  }
  if (count === 3) {
    const runningSections = Object.fromEntries(
      ALL_SECTION_SLUGS.map((slug) => [
        slug,
        { state: "running", attempt_id: ATTEMPT_ID },
      ]),
    );
    return jobState({ status: "analyzing", sections: runningSections });
  }
  return jobState({ status: "done", sections: allDoneSections() });
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
      response.end(JSON.stringify(jobStateForCount(pollCount)));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${FAILED_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify(
          jobState({
            jobId: FAILED_JOB_ID,
            status: "failed",
            errorCode: "unsafe_url",
            errorMessage: "Blocked by web_risk",
          }),
        ),
      );
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${CACHED_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify(
          jobState({
            jobId: CACHED_JOB_ID,
            status: "done",
            sections: allDoneSections(),
            cached: true,
          }),
        ),
      );
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
  pollCount = 0;
});

test("AC5: extracting indicator is visible during extracting and disappears on done", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`);

  const indicator = page.locator('[data-testid="extracting-indicator"]');
  const sidebar = page.locator('[data-testid="analysis-sidebar"]');

  // The indicator must be visible while the job is in the extracting phase.
  await expect(indicator).toBeVisible({ timeout: 10_000 });
  await expect(sidebar).toHaveAttribute("data-job-status", "extracting");

  // Per AC1: every section slot must be in `running` state during extracting
  // so that the per-slug content-shape skeleton renders. This is what
  // produces the motion-bearing visual the user sees in the sidebar.
  for (const slug of ALL_SECTION_SLUGS) {
    await expect(page.locator(`[data-testid="slot-${slug}"]`)).toHaveAttribute(
      "data-slot-state",
      "running",
      { timeout: 10_000 },
    );
  }

  // The indicator's pulse marker must use the shared .skeleton-pulse class
  // so motion is uniform with the per-slug skeletons.
  const pulseCount = await indicator.locator(".skeleton-pulse").count();
  expect(pulseCount).toBeGreaterThan(0);

  // AC3 smooth handoff: once status flips to `analyzing` the indicator is
  // gone but per-slot skeletons remain mounted (still in `running`). We
  // assert by waiting for the data-job-status attribute to flip.
  await expect(sidebar).toHaveAttribute("data-job-status", "analyzing", {
    timeout: 10_000,
  });
  await expect(indicator).toHaveCount(0);

  // The per-slot skeletons should still be mounted during analyzing —
  // proves continuity of the visual feedback across the handoff.
  for (const slug of ALL_SECTION_SLUGS) {
    await expect(page.locator(`[data-testid="slot-${slug}"]`)).toHaveAttribute(
      "data-slot-state",
      "running",
    );
  }

  // Eventually status reaches `done`; indicator stays absent and slots
  // flip to `done`.
  await expect(sidebar).toHaveAttribute("data-job-status", "done", {
    timeout: 15_000,
  });
  await expect(indicator).toHaveCount(0);
  for (const slug of ALL_SECTION_SLUGS) {
    await expect(page.locator(`[data-testid="slot-${slug}"]`)).toHaveAttribute(
      "data-slot-state",
      "done",
      { timeout: 15_000 },
    );
  }
});

test("AC4 negative: failed-job path shows the failure card and never the extracting indicator", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${FAILED_JOB_ID}`);

  // Failure card must appear; sidebar (and therefore the indicator)
  // must not.
  await expect(page.locator('[data-testid="job-failure-card"]')).toBeVisible({
    timeout: 10_000,
  });
  await expect(
    page.locator('[data-testid="extracting-indicator"]'),
  ).toHaveCount(0);
  await expect(page.locator('[data-testid="analysis-sidebar"]')).toHaveCount(0);
});

test("AC4 negative: cached-hit (status=done on first poll) never shows the extracting indicator", async ({
  page,
}) => {
  // The cached job's first (and only) poll returns status=done with all
  // sections seeded. The indicator must never become visible.
  await page.goto(`${webBaseUrl}/analyze?job=${CACHED_JOB_ID}`);

  // Wait for sidebar to mount and confirm the data-job-status flipped
  // straight to "done" without ever passing through "extracting".
  const sidebar = page.locator('[data-testid="analysis-sidebar"]');
  await expect(sidebar).toBeVisible({ timeout: 10_000 });
  await expect(sidebar).toHaveAttribute("data-job-status", "done", {
    timeout: 10_000,
  });

  // Indicator must not appear at any point.
  await expect(
    page.locator('[data-testid="extracting-indicator"]'),
  ).toHaveCount(0);
});
