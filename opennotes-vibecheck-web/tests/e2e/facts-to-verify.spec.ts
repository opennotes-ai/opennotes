import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { createServer, type Server } from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";
import { ALL_SECTION_SLUGS } from "./fixtures/quizlet";

const FACTS_JOB_ID = "77777777-7777-7777-8777-777777777777";
const ATTEMPT_ID = "88888888-8888-7888-8888-888888888888";
const SOURCE_URL = "https://example.test/ab-259-analysis";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));

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

function claimsReport(): Record<string, unknown> {
  return {
    deduped_claims: [
      {
        canonical_text: "AB-259 would create a California wealth tax.",
        category: "potentially_factual",
        occurrence_count: 2,
        author_count: 2,
        utterance_ids: ["u-1", "u-3"],
        representative_authors: ["Alice", "Casey"],
        supporting_facts: [],
        facts_to_verify: 3,
      },
      {
        canonical_text: "The proposal would apply only above a high asset threshold.",
        category: "potentially_factual",
        occurrence_count: 1,
        author_count: 1,
        utterance_ids: ["u-2"],
        representative_authors: ["Blair"],
        supporting_facts: [
          {
            statement: "A different grounded statement describes the threshold.",
            source_kind: "utterance",
            source_ref: "u-2",
          },
        ],
        facts_to_verify: 0,
      },
    ],
    total_claims: 3,
    total_unique: 2,
  };
}

function sectionData(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") return { harmful_content_matches: [] };
  if (slug === "safety__web_risk") return { findings: [], urls_checked: 0 };
  if (slug === "safety__image_moderation") return { matches: [] };
  if (slug === "safety__video_moderation") return { matches: [] };
  if (slug === "tone_dynamics__flashpoint") return { flashpoint_matches: [] };
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "The discussion stays focused on factual policy details.",
        summary: "Factual policy discussion.",
        tone_labels: ["informational"],
        per_speaker_notes: {},
        speaker_arcs: [],
        insufficient_conversation: false,
      },
    };
  }
  if (
    slug === "facts_claims__dedup" ||
    slug === "facts_claims__evidence" ||
    slug === "facts_claims__premises"
  ) {
    return { claims_report: claimsReport() };
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
  if (slug === "opinions_sentiments__trends_oppositions") {
    return {
      trends_oppositions_report: {
        trends: [],
        oppositions: [],
        fallback_engaged: false,
      },
    };
  }
  if (slug === "opinions_sentiments__highlights") {
    return {
      highlights_report: {
        highlights: [],
        fallback_engaged: false,
        floor_eligible_count: 0,
        total_input_count: 0,
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
        finished_at: "2026-05-07T01:30:00Z",
      },
    ]),
  );
}

function sidebarPayload(): Record<string, unknown> {
  return {
    cached_at: "2026-05-07T01:30:00Z",
    safety: { harmful_content_matches: [], recommendation: null },
    web_risk: { findings: [], urls_checked: 0 },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      flashpoint_matches: [],
      scd: sectionData("tone_dynamics__scd").scd,
    },
    facts_claims: {
      claims_report: claimsReport(),
      evidence_status: "done",
      premises_status: "done",
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

function terminalJobState(): Record<string, unknown> {
  return {
    job_id: FACTS_JOB_ID,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    error_code: null,
    error_message: null,
    error_host: null,
    created_at: "2026-05-07T01:29:00Z",
    updated_at: "2026-05-07T01:30:00Z",
    sections: allDoneSections(),
    sidebar_payload: sidebarPayload(),
    sidebar_payload_complete: true,
    activity_label: null,
    activity_at: null,
    cached: true,
    next_poll_ms: 1500,
    page_title: "AB-259 policy analysis",
    page_kind: "article",
    utterance_count: 3,
  };
}

async function gotoAnalyze(page: Page): Promise<void> {
  await page.goto(`${webBaseUrl}/analyze?job=${FACTS_JOB_ID}`);
  await expect(page.getByTestId("analysis-sidebar")).toHaveAttribute(
    "data-job-status",
    "done",
    { timeout: 15_000 },
  );
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${FACTS_JOB_ID}`
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(terminalJobState()));
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

test("mocked completed job renders facts-to-verify as verification evidence", async ({
  page,
}, testInfo) => {
  await gotoAnalyze(page);

  const claimItems = page.getByTestId("deduped-claim-item");
  await expect(claimItems).toHaveCount(2);

  const needsVerificationClaim = claimItems.nth(0);
  const groundedClaim = claimItems.nth(1);

  await expect(
    needsVerificationClaim.getByTestId("deduped-claim-facts-to-verify"),
  ).toHaveText("3 facts to verify");
  await expect(
    needsVerificationClaim.getByTestId("deduped-claim-supporting-fact"),
  ).toHaveCount(0);
  await expect(
    groundedClaim.getByTestId("deduped-claim-supporting-fact"),
  ).toContainText("A different grounded statement describes the threshold.");
  await expect(
    groundedClaim.getByTestId("deduped-claim-facts-to-verify"),
  ).toHaveCount(0);

  await expect(
    needsVerificationClaim.locator(
      '[data-testid="deduped-claim-supporting-fact"], [data-testid="deduped-claim-facts-to-verify"]',
    ),
  ).toHaveCount(1);
  await expect(
    groundedClaim.locator(
      '[data-testid="deduped-claim-supporting-fact"], [data-testid="deduped-claim-facts-to-verify"]',
    ),
  ).toHaveCount(1);

  const parentClaimText = (
    await groundedClaim.getByTestId("deduped-claim-text").textContent()
  )?.trim().toLowerCase();
  const supportingFactText = (
    await groundedClaim
      .getByTestId("deduped-claim-supporting-fact")
      .locator("span")
      .first()
      .textContent()
  )?.trim().toLowerCase();
  expect(supportingFactText).toBe(
    "a different grounded statement describes the threshold.",
  );
  expect(supportingFactText).not.toBe(parentClaimText);

  const chip = needsVerificationClaim.getByTestId(
    "deduped-claim-facts-to-verify",
  );
  await chip.scrollIntoViewIfNeeded();
  await expect(chip).toBeVisible();
  const screenshotPath = testInfo.outputPath("facts-to-verify-chip.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });
  expect(screenshotPath).toBeTruthy();
});
