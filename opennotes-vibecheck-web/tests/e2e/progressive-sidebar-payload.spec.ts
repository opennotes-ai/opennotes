import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

/**
 * TASK-1473.65.07 — Progressive sidebar payload poll sequence and cache-hit
 * no-flash verification.
 *
 * Drives a job through a scripted mock-API state machine:
 *
 *   poll 1  → extracting, sections empty, sidebar_payload=null
 *   poll 2  → analyzing, one done slot + one running slot,
 *             sidebar_payload=aggregate defaults, sidebar_payload_complete=false
 *   poll 3+ → done, all slots done, sidebar_payload_complete=true
 *
 * Asserts:
 *
 *   1. During analyzing the done slot renders real report content (not a
 *      skeleton) while the running slot keeps its skeleton visible.
 *   2. Once the terminal poll arrives, every slot flips to done, skeletons
 *      disappear, and sidebar_payload_complete=true stops polling.
 *   3. A cache-hit first render (done + sidebar_payload_complete=true from
 *      t=0) never shows the extracting indicator and never mounts skeletons.
 */

const JOB_ID = "55555555-5555-7555-8555-555555555555";
const CACHED_JOB_ID = "66666666-6666-7666-8666-666666666666";
const ATTEMPT_ID = "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb";
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

async function expectAppToStayMounted(page: Page) {
  await expect
    .poll(async () =>
      page.locator("#app").evaluate((node) => node.innerHTML.length),
    )
    .toBeGreaterThan(100);
}

function sectionDataFor(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") {
    return {
      harmful_content_matches: [
        {
          source: "openai",
          utterance_id: "u-0",
          utterance_text: "Test match text",
          max_score: 0.85,
          flagged_categories: ["harassment"],
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

interface JobStateOverrides {
  jobId?: string;
  status: "pending" | "extracting" | "analyzing" | "done" | "failed";
  sections?: Record<string, unknown>;
  cached?: boolean;
  sidebarPayload?: Record<string, unknown> | null;
  sidebarPayloadComplete?: boolean;
  activityLabel?: string | null;
}

function jobState(overrides: JobStateOverrides): Record<string, unknown> {
  return {
    job_id: overrides.jobId ?? JOB_ID,
    url: SOURCE_URL,
    status: overrides.status,
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections: overrides.sections ?? {},
    sidebar_payload: overrides.sidebarPayload ?? null,
    sidebar_payload_complete: overrides.sidebarPayloadComplete ?? false,
    activity_label: overrides.activityLabel ?? null,
    activity_at: overrides.activityLabel ? "2026-04-23T22:09:00Z" : null,
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

function aggregateDefaultsPayload(): Record<string, unknown> {
  return {
    source_url: SOURCE_URL,
    page_title: null,
    page_kind: "other",
    scraped_at: "2026-04-23T22:08:00Z",
    cached: false,
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

function jobStateForCount(jobId: string, count: number): Record<string, unknown> {
  // Three-phase deterministic state machine.
  //   polls 1-2  → extracting (empty sections, no payload)
  //   polls 3-5  → analyzing (one done + one running, aggregate defaults payload)
  //   poll 6+    → done (all slots done, complete payload)
  if (count <= 2) {
    return jobState({
      jobId,
      status: "extracting",
      sections: {},
      sidebarPayload: null,
      sidebarPayloadComplete: false,
      activityLabel: "Extracting page content",
    });
  }
  if (count >= 3 && count <= 5) {
    const sections: Record<string, unknown> = {
      safety__moderation: {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionDataFor("safety__moderation"),
        finished_at: "2026-04-23T22:09:00Z",
      },
      safety__web_risk: {
        state: "running",
        attempt_id: ATTEMPT_ID,
      },
    };
    return jobState({
      jobId,
      status: "analyzing",
      sections,
      sidebarPayload: aggregateDefaultsPayload(),
      sidebarPayloadComplete: false,
      activityLabel: "Running section analyses",
    });
  }
  return jobState({
    jobId,
    status: "done",
    sections: allDoneSections(),
    sidebarPayload: aggregateDefaultsPayload(),
    sidebarPayloadComplete: true,
  });
}

function nextJobState(jobId: string): Record<string, unknown> {
  const count = (pollCounts.get(jobId) ?? 0) + 1;
  pollCounts.set(jobId, count);
  return jobStateForCount(jobId, count);
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(nextJobState(JOB_ID)));
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
            sidebarPayload: aggregateDefaultsPayload(),
            sidebarPayloadComplete: true,
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
  pollCounts = new Map<string, number>();
});

test("AC1: analyzing phase shows real content for done slot and skeleton for running slot", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`);

  const sidebar = page.locator('[data-testid="analysis-sidebar"]');
  const indicator = page.locator('[data-testid="extracting-indicator"]');

  // Extracting phase: indicator visible, all slots synthesized as running.
  await expect(indicator).toBeVisible({ timeout: 10_000 });
  await expect(sidebar).toHaveAttribute("data-job-status", "extracting", {
    timeout: 10_000,
  });
  await expectAppToStayMounted(page);

  // Transition to analyzing: indicator stays visible with new label.
  await expect(sidebar).toHaveAttribute("data-job-status", "analyzing", {
    timeout: 10_000,
  });
  await expect(indicator).toBeVisible({ timeout: 10_000 });
  await expect(indicator).toContainText("Running section analyses", {
    timeout: 10_000,
  });

  // The done slot must NOT contain a skeleton — real report content is
  // rendered instead. Because harmful_content_matches is non-empty the
  // section body defaults to open.
  const doneSlot = page.locator('[data-testid="slot-safety__moderation"]');
  await expect(doneSlot).toHaveAttribute("data-slot-state", "done", {
    timeout: 10_000,
  });
  await expect(
    doneSlot.locator('[data-testid="skeleton-safety__moderation"]'),
  ).toHaveCount(0);
  await expect(
    doneSlot.locator('[data-testid="report-safety__moderation"]'),
  ).toBeVisible({ timeout: 10_000 });

  // The running slot must contain its skeleton.
  const runningSlot = page.locator('[data-testid="slot-safety__web_risk"]');
  await expect(runningSlot).toHaveAttribute("data-slot-state", "running", {
    timeout: 10_000,
  });
  // Safety-related skeletons reuse the same component; assert by class.
  await expect(
    runningSlot.locator(".skeleton-pulse").first(),
  ).toBeVisible({ timeout: 10_000 });

  // Pending slots have no body rendered at all.
  const pendingSlot = page.locator('[data-testid="slot-tone_dynamics__scd"]');
  await expect(pendingSlot).toHaveAttribute("data-slot-state", "pending");

  await expectAppToStayMounted(page);
});

test("AC2: terminal poll removes skeletons and shows complete content", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`);

  const sidebar = page.locator('[data-testid="analysis-sidebar"]');

  // Wait until the job reaches done.
  await expect(sidebar).toHaveAttribute("data-job-status", "done", {
    timeout: 15_000,
  });

  // Extracting indicator must be gone.
  await expect(
    page.locator('[data-testid="extracting-indicator"]'),
  ).toHaveCount(0);

  // Every slot must be done and contain no skeletons.
  for (const slug of ALL_SECTION_SLUGS) {
    const slot = page.locator(`[data-testid="slot-${slug}"]`);
    await expect(slot).toHaveAttribute("data-slot-state", "done", {
      timeout: 15_000,
    });
    await expect(
      slot.locator(`[data-testid="skeleton-${slug}"]`),
    ).toHaveCount(0);
  }

  await expectAppToStayMounted(page);
});

test("AC3: cache-hit first render has no extracting indicator and no skeleton flash", async ({
  page,
}) => {
  // The cached job's first (and only) poll returns done with
  // sidebar_payload_complete=true. The sidebar must synthesize every
  // section from the payload immediately, so there is no skeleton
  // mount at any point.
  await page.goto(`${webBaseUrl}/analyze?job=${CACHED_JOB_ID}&c=1`);

  const sidebar = page.locator('[data-testid="analysis-sidebar"]');
  await expect(sidebar).toBeVisible({ timeout: 10_000 });

  // Status must reach done without ever showing extracting.
  await expect(sidebar).toHaveAttribute("data-job-status", "done", {
    timeout: 10_000,
  });

  // Extracting indicator must never appear.
  await expect(
    page.locator('[data-testid="extracting-indicator"]'),
  ).toHaveCount(0);

  // No skeleton should exist for any slot — the payload synthesis path
  // renders every section as done from the first paint.
  for (const slug of ALL_SECTION_SLUGS) {
    const slot = page.locator(`[data-testid="slot-${slug}"]`);
    await expect(slot).toHaveAttribute("data-slot-state", "done", {
      timeout: 10_000,
    });
    await expect(
      slot.locator(`[data-testid="skeleton-${slug}"]`),
    ).toHaveCount(0);
  }

  await expectAppToStayMounted(page);
});
