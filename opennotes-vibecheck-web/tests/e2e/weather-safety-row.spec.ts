import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

/**
 * TASK-1569.10.06 — Playwright E2E: safety row + popover pulse + isolate-section button.
 *
 * Verifies:
 *   AC1: 4 weather rows are visible with Safety first; safety pill text in
 *        ["Safe", "Mild", "Caution", "Unsafe"].
 *   AC2: Clicking the safety pill trigger sets data-highlighted="true" on
 *        section-group-Safety; closing the popover removes the attribute.
 *   AC3: Clicking the weather-safety-focus button collapses the other 3
 *        SectionGroups while leaving Safety expanded.
 *   AC4: Cross-axis isolate works for at least one other axis — truth pill
 *        focus button leaves only Facts/claims expanded.
 *   AC5: Reduced-motion passthrough — open safety popover, assert
 *        data-highlighted="true" is set; no animation assertions.
 */

const SOURCE_URL = "https://quizlet.com/blog/groups-are-now-classes/";
const SAFETY_JOB_ID = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";
const ATTEMPT_ID = "dddddddd-dddd-7ddd-8ddd-dddddddddddd";

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

function sectionDataFor(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") return { harmful_content_matches: [] };
  if (slug === "safety__web_risk") return { findings: [], urls_checked: 0 };
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

function safetyDonePayload(safetyLevel: string): Record<string, unknown> {
  return {
    source_url: SOURCE_URL,
    page_title: "Groups are now classes",
    page_kind: "article",
    scraped_at: "2026-04-23T22:08:00Z",
    cached: false,
    headline: {
      text: "A concise lead-in summary derived from the conversation.",
      kind: "synthesized",
      source: "server",
      unavailable_inputs: [],
    },
    weather_report: {
      truth: { label: "first_person", logprob: null, alternatives: [] },
      relevance: { label: "on_topic", logprob: null, alternatives: [] },
      sentiment: { label: "neutral", logprob: null, alternatives: [] },
    },
    safety: {
      harmful_content_matches: [],
      recommendation: {
        level: safetyLevel,
        rationale: "All safety checks passed cleanly.",
      },
    },
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

function pendingState(jobId: string): Record<string, unknown> {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "pending",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:08:00Z",
    sections: {},
    sidebar_payload: null,
    sidebar_payload_complete: false,
    activity_label: "Preparing analysis",
    activity_at: "2026-04-23T22:08:00Z",
    cached: false,
    next_poll_ms: 250,
    page_title: null,
    page_kind: null,
    utterance_count: 0,
  };
}

function doneState(jobId: string, safetyLevel: string): Record<string, unknown> {
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections: allDoneSections(),
    sidebar_payload: safetyDonePayload(safetyLevel),
    sidebar_payload_complete: true,
    activity_label: null,
    activity_at: null,
    cached: false,
    next_poll_ms: 1500,
    page_title: "Groups are now classes",
    page_kind: "article",
    utterance_count: 3,
  };
}

function nextPoll(jobId: string, safetyLevel: string): Record<string, unknown> {
  const count = (pollCounts.get(jobId) ?? 0) + 1;
  pollCounts.set(jobId, count);
  if (count <= 2) return pendingState(jobId);
  return doneState(jobId, safetyLevel);
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");

    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${SAFETY_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(nextPoll(SAFETY_JOB_ID, "safe")));
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

async function navigateToSafetyJob(page: import("@playwright/test").Page): Promise<void> {
  await page.goto(`${webBaseUrl}/analyze?job=${SAFETY_JOB_ID}`);
  await expect(page.locator('[data-testid="weather-report"]')).toBeVisible({
    timeout: 15_000,
  });
}

test("AC1: 4 weather rows visible with Safety first; safety pill text is one of Safe/Mild/Caution/Unsafe", async ({
  page,
}) => {
  await navigateToSafetyJob(page);

  const weatherReport = page.locator('[data-testid="weather-report"]');

  const safetyPill = weatherReport.locator('[data-testid="weather-safety-value"]');
  await expect(safetyPill).toBeVisible();
  const safetyText = await safetyPill.textContent();
  expect(["Safe", "Mild", "Caution", "Unsafe"]).toContain(safetyText?.trim());

  await expect(weatherReport.locator('[data-testid="weather-axis-card-safety"]')).toBeVisible();
  await expect(weatherReport.locator('[data-testid="weather-axis-card-truth"]')).toBeVisible();
  await expect(weatherReport.locator('[data-testid="weather-axis-card-relevance"]')).toBeVisible();
  await expect(weatherReport.locator('[data-testid="weather-axis-card-sentiment"]')).toBeVisible();

  const axisTriggers = weatherReport.locator('[data-testid^="weather-axis-card-"]');
  const count = await axisTriggers.count();
  expect(count).toBe(4);

  const firstTriggerTestId = await axisTriggers.first().getAttribute("data-testid");
  expect(firstTriggerTestId).toBe("weather-axis-card-safety");
});

test("AC2: clicking safety pill sets data-highlighted=true on safety SectionGroup; closing removes it", async ({
  page,
}) => {
  await navigateToSafetyJob(page);

  const safetyGroup = page.locator('[data-testid="section-group-Safety"]');
  const safetyTrigger = page.locator('[data-testid="weather-axis-card-safety"]');

  await expect(safetyGroup).not.toHaveAttribute("data-highlighted", "true");

  await safetyTrigger.click();

  await expect(safetyGroup).toHaveAttribute("data-highlighted", "true");

  await page.keyboard.press("Escape");

  await expect(safetyGroup).not.toHaveAttribute("data-highlighted", "true");
});

test("AC3: clicking weather-safety-focus collapses the other 3 SectionGroups, Safety stays expanded", async ({
  page,
}) => {
  await navigateToSafetyJob(page);

  const safetyTrigger = page.locator('[data-testid="weather-axis-card-safety"]');
  await safetyTrigger.click();

  const focusButton = page.locator('[data-testid="weather-safety-focus"]');
  await expect(focusButton).toBeVisible();
  await focusButton.click();

  const safetyToggle = page.locator('[data-testid="section-toggle-Safety"]');
  await expect(safetyToggle).toHaveAttribute("aria-expanded", "true");

  const toneToggle = page.locator('[data-testid="section-toggle-Tone/dynamics"]');
  await expect(toneToggle).toHaveAttribute("aria-expanded", "false");

  const factsToggle = page.locator('[data-testid="section-toggle-Facts/claims"]');
  await expect(factsToggle).toHaveAttribute("aria-expanded", "false");

  const opinionsToggle = page.locator('[data-testid="section-toggle-Opinions"]');
  await expect(opinionsToggle).toHaveAttribute("aria-expanded", "false");

  // Sentiments is sticky-open and must remain expanded through isolateGroup
  // (parent TASK-1633 AC #2).
  const sentimentsToggle = page.locator('[data-testid="section-toggle-Sentiments"]');
  await expect(sentimentsToggle).toHaveAttribute("aria-expanded", "true");
});

test("AC4: clicking weather-truth-focus collapses other 3 SectionGroups, Facts/claims stays expanded", async ({
  page,
}) => {
  await navigateToSafetyJob(page);

  const truthTrigger = page.locator('[data-testid="weather-axis-card-truth"]');
  await truthTrigger.click();

  const focusButton = page.locator('[data-testid="weather-truth-focus"]');
  await expect(focusButton).toBeVisible();
  await focusButton.click();

  const factsToggle = page.locator('[data-testid="section-toggle-Facts/claims"]');
  await expect(factsToggle).toHaveAttribute("aria-expanded", "true");

  const safetyToggle = page.locator('[data-testid="section-toggle-Safety"]');
  await expect(safetyToggle).toHaveAttribute("aria-expanded", "false");

  const toneToggle = page.locator('[data-testid="section-toggle-Tone/dynamics"]');
  await expect(toneToggle).toHaveAttribute("aria-expanded", "false");

  const opinionsToggle = page.locator('[data-testid="section-toggle-Opinions"]');
  await expect(opinionsToggle).toHaveAttribute("aria-expanded", "false");

  // Sentiments is sticky-open and must remain expanded through isolateGroup
  // (parent TASK-1633 AC #2).
  const sentimentsToggle = page.locator('[data-testid="section-toggle-Sentiments"]');
  await expect(sentimentsToggle).toHaveAttribute("aria-expanded", "true");
});

test("AC5: reduced-motion passthrough — safety popover open still sets data-highlighted=true and changes computed bg-color", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await navigateToSafetyJob(page);

  const safetyGroup = page.locator('[data-section-group="Safety"]');
  const safetyTrigger = page.locator('[data-testid="weather-axis-card-safety"]');

  const beforeBg = await safetyGroup.evaluate((el) => getComputedStyle(el).backgroundColor);

  await safetyTrigger.click();

  await expect(safetyGroup).toHaveAttribute("data-highlighted", "true");

  const afterBg = await safetyGroup.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(afterBg).not.toBe(beforeBg);

  await page.keyboard.press("Escape");

  await expect(safetyGroup).not.toHaveAttribute("data-highlighted", "true");
});
