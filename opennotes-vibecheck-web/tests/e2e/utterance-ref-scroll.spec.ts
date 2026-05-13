import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const ARCHIVE_JOB_ID = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
const NO_ARCHIVE_JOB_ID = "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb";
const ATTEMPT_ID = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const SCREENSHOT_URL =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='800'%3E%3Crect width='1200' height='800' fill='%23f8fafc'/%3E%3C/svg%3E";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";

async function runWebCommand(args: string[], env: NodeJS.ProcessEnv): Promise<void> {
  const child = spawn("pnpm", args, {
    cwd: WEB_ROOT,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout?.on("data", (chunk) => {
    output += chunk.toString();
  });
  child.stderr?.on("data", (chunk) => {
    output += chunk.toString();
  });
  const [code, signal] = (await once(child, "exit")) as [
    number | null,
    NodeJS.Signals | null,
  ];
  if (code !== 0) {
    throw new Error(
      `pnpm ${args.join(" ")} failed code=${code} signal=${signal}\n${output}`,
    );
  }
}

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
  let lastError: unknown = null;
  await expect
    .poll(
      async () => {
        try {
          const response = await fetch(url);
          return response.ok;
        } catch (error) {
          lastError = error;
          return false;
        }
      },
      {
        intervals: [250],
        timeout: timeoutMs,
        message: `Timed out waiting for ${url}. Last error: ${
          lastError instanceof Error ? lastError.message : String(lastError)
        }\n${webLogs}`,
      },
    )
    .toBe(true);
}

async function stopWebProcess(process: ChildProcess): Promise<void> {
  if (process.exitCode !== null || process.signalCode !== null) return;

  const exitPromise = once(process, "exit").then(() => undefined);
  process.kill("SIGTERM");
  const exited = await Promise.race([
    exitPromise.then(() => true),
    delay(5_000).then(() => false),
  ]);

  if (!exited && process.exitCode === null && process.signalCode === null) {
    process.kill("SIGKILL");
    await exitPromise;
  }
}

function writeJson(
  response: ServerResponse<IncomingMessage>,
  status: number,
  body: unknown,
): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function jobState(jobId: string) {
  const path = jobId === ARCHIVE_JOB_ID ? "article-with-archive" : "article-no-archive";
  return {
    job_id: jobId,
    url: `${apiBaseUrl}/${path}`,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-24T18:00:00Z",
    updated_at: "2026-04-24T18:00:01Z",
    sections: {},
    sidebar_payload: sidebarPayload(),
    cached: false,
    next_poll_ms: 1500,
    page_title: "Utterance scroll fixture",
    page_kind: "article",
    utterance_count: 6,
  };
}

function sidebarPayload() {
  return {
    headline: null,
    utterances: [
      { position: 1, utterance_id: "post-0-aaa" },
      { position: 2, utterance_id: "comment-1-bbb" },
      { position: 3, utterance_id: "comment-2-ccc" },
      { position: 4, utterance_id: "reply-3-ddd" },
      { position: 5, utterance_id: "comment-4-eee" },
      { position: 6, utterance_id: "comment-5-fff" },
    ],
    safety: {
      recommendation: null,
      harmful_content_matches: [
        {
          utterance_id: "post-0-aaa",
          utterance_text: "",
          max_score: 0.91,
          flagged_categories: ["harassment"],
          categories: { harassment: true },
          scores: {},
          source: "openai",
        },
      ],
    },
    web_risk: { findings: [] },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      flashpoint_matches: [
        {
          scan_type: "conversation_flashpoint",
          utterance_id: "comment-1-bbb",
          derailment_score: 88,
          risk_level: "Heated",
          reasoning: "The exchange becomes confrontational.",
        },
      ],
      scd: {
        summary: "The conversation shifts from neutral to tense.",
        narrative: "A short speaker arc connects the claim to the source.",
        tone_labels: ["tense"],
        per_speaker_notes: {},
        speaker_arcs: [
          {
            speaker: "Alex",
            note: "Pushes the disagreement forward.",
            utterance_id_range: [3, 3],
          },
        ],
        insufficient_conversation: false,
      },
    },
    facts_claims: {
      claims_report: {
        deduped_claims: [
          {
            canonical_text: "The same factual claim appears twice.",
            occurrence_count: 2,
            author_count: 1,
            utterance_ids: ["comment-4-eee", "reply-3-ddd"],
          },
        ],
        total_claims: 2,
        total_unique: 1,
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
        subjective_claims: [
          {
            utterance_id: "comment-5-fff",
            claim_text: "This is the best possible interpretation.",
            stance: "opinion",
          },
        ],
      },
    },
    cached_at: null,
  };
}

function archiveHtml(): string {
  return `<!doctype html>
    <html>
      <head>
        <style>
          body { margin: 0; font-family: Arial, sans-serif; line-height: 1.5; }
          article { padding: 32px; }
          p { margin: 0 0 24px; padding: 16px; border: 1px solid #d4d4d8; }
          .spacer { height: 760px; border: 0; padding: 0; }
        </style>
      </head>
      <body>
        <article>
          <p data-utterance-id="post-0-aaa">Source post near the top.</p>
          <div class="spacer"></div>
          <p data-utterance-id="comment-1-bbb">Flashpoint comment in the middle.</p>
          <div class="spacer"></div>
          <p data-utterance-id="comment-2-ccc">Speaker dynamics comment.</p>
          <div class="spacer"></div>
          <p data-utterance-id="comment-4-eee">Deduped claim comment.</p>
          <div class="spacer"></div>
          <p data-utterance-id="reply-3-ddd">Additional deduped claim reply.</p>
          <div class="spacer"></div>
          <p data-utterance-id="comment-5-fff">Subjective claim comment near the bottom.</p>
        </article>
      </body>
    </html>`;
}

async function gotoAnalyze(page: Page, jobId = ARCHIVE_JOB_ID): Promise<void> {
  await page.goto(`${webBaseUrl}/analyze?job=${jobId}`);
  await expect(page.getByTestId("analysis-sidebar")).toBeVisible();
}

function archiveFrame(page: Page): FrameLocator {
  return page.frameLocator('[data-testid="page-frame-archived-iframe"]');
}

async function waitForArchivedFrame(page: Page): Promise<void> {
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible();
  await expect(archiveFrame(page).locator('[data-utterance-id="post-0-aaa"]')).toBeVisible();
}

async function iframeScrollY(page: Page): Promise<number> {
  return archiveFrame(page).locator("body").evaluate(() => window.scrollY);
}

async function setIframeScrollY(page: Page, y: number): Promise<void> {
  await archiveFrame(page).locator("body").evaluate((_, scrollY) => {
    window.scrollTo(0, scrollY);
  }, y);
}

function utteranceTarget(page: Page, utteranceId: string): Locator {
  return archiveFrame(page).locator(`[data-utterance-id="${utteranceId}"]`);
}

async function expectOnlyRing(page: Page, utteranceId: string): Promise<void> {
  await expect(utteranceTarget(page, utteranceId)).toHaveAttribute(
    "data-vibecheck-ring",
    "",
  );
  await expect(archiveFrame(page).locator("[data-vibecheck-ring]")).toHaveCount(1);
}

async function expectTargetInViewport(page: Page, utteranceId: string): Promise<void> {
  await expect
    .poll(async () =>
      utteranceTarget(page, utteranceId).evaluate((el) => {
        const rect = el.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= window.innerHeight;
      }),
    )
    .toBe(true);
}

async function activateAndExpectJump(
  page: Page,
  ref: Locator,
  utteranceId: string,
  mode: "click" | "enter" | "space" = "click",
): Promise<void> {
  if (mode === "enter") {
    await ref.focus();
    await page.keyboard.press("Enter");
  } else if (mode === "space") {
    await ref.focus();
    await page.keyboard.press("Space");
  } else {
    await ref.click();
  }
  await expectOnlyRing(page, utteranceId);
  await expectTargetInViewport(page, utteranceId);
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${ARCHIVE_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(ARCHIVE_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${NO_ARCHIVE_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(NO_ARCHIVE_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      writeJson(response, 200, {
        can_iframe: true,
        blocking_header: null,
        csp_frame_ancestors: null,
        has_archive: targetUrl.includes("/article-with-archive"),
      });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/archive-preview"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      const jobId = requestUrl.searchParams.get("job_id") ?? "";
      if (targetUrl.includes("/article-with-archive") && jobId === ARCHIVE_JOB_ID) {
        response.writeHead(200, {
          "cache-control": "no-store, private",
          "content-type": "text/html; charset=utf-8",
        });
        response.end(archiveHtml());
        return;
      }
      writeJson(response, 404, { detail: "Archive unavailable" });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/screenshot"
    ) {
      writeJson(response, 200, { screenshot_url: SCREENSHOT_URL });
      return;
    }
    if (
      request.method === "GET" &&
      (requestUrl.pathname === "/article-with-archive" ||
        requestUrl.pathname === "/article-no-archive")
    ) {
      response.writeHead(200, { "content-type": "text/html" });
      response.end("<!doctype html><h1>Original article fixture</h1>");
      return;
    }
    writeJson(response, 404, { error_code: "not_found" });
  });
  const apiPort = await listenOnRandomPort(apiServer);
  apiBaseUrl = `http://127.0.0.1:${apiPort}`;

  const webPort = await findFreePort();
  webBaseUrl = `http://127.0.0.1:${webPort}`;
  const webEnv = {
    ...process.env,
    VIBECHECK_SERVER_URL: apiBaseUrl,
    VIBECHECK_WEB_PORT: String(webPort),
    HOST: "127.0.0.1",
    PORT: String(webPort),
  };

  await runWebCommand(["run", "build"], webEnv);
  webProcess = spawn(
    "pnpm",
    ["run", "start", "--port", String(webPort), "--host", "127.0.0.1"],
    {
      cwd: WEB_ROOT,
      env: webEnv,
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

test("utterance refs switch to archive, scroll to five report targets, and move the active ring", async ({
  page,
}) => {
  await gotoAnalyze(page);

  await expect(page.getByTestId("safety-utterance-ref")).toHaveText("main post");
  await expect(page.getByTestId("flashpoint-utterance-ref")).toHaveText("comment #1");
  await expect(page.getByTestId("subjective-claim-utterance-ref")).toHaveText("comment #4");
  await expect(page.getByTestId("deduped-claim-utterance-ref")).toHaveText("comment #3");

  await page.getByTestId("flashpoint-utterance-ref").click();
  await waitForArchivedFrame(page);
  await expectOnlyRing(page, "comment-1-bbb");
  await expectTargetInViewport(page, "comment-1-bbb");
  await expect(page.getByRole("button", { name: "Snapshot" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await setIframeScrollY(page, 0);
  await activateAndExpectJump(
    page,
    page.getByTestId("safety-utterance-ref"),
    "post-0-aaa",
    "enter",
  );

  const belowStart = await iframeScrollY(page);
  await activateAndExpectJump(
    page,
    page.getByTestId("subjective-claim-utterance-ref"),
    "comment-5-fff",
    "space",
  );
  await expect.poll(async () => iframeScrollY(page)).toBeGreaterThan(belowStart);

  await activateAndExpectJump(
    page,
    page.getByTestId("scd-arc-range"),
    "comment-2-ccc",
  );

  await activateAndExpectJump(
    page,
    page.getByTestId("deduped-claim-utterance-ref"),
    "comment-4-eee",
  );
});

test("utterance refs scroll upward when the archived target was already passed", async ({
  page,
}) => {
  await gotoAnalyze(page);
  await page.getByRole("button", { name: "Snapshot" }).click();
  await waitForArchivedFrame(page);

  await setIframeScrollY(page, 4_000);
  await expect.poll(async () => iframeScrollY(page)).toBeGreaterThan(1_000);
  await activateAndExpectJump(
    page,
    page.getByTestId("safety-utterance-ref"),
    "post-0-aaa",
  );
  await expect.poll(async () => iframeScrollY(page)).toBeLessThan(500);
});

test("no-archive jobs render utterance refs as inert and do not switch preview mode", async ({
  page,
}) => {
  await gotoAnalyze(page, NO_ARCHIVE_JOB_ID);
  await expect(page.getByTestId("page-frame-iframe")).toBeVisible();
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveCount(0);

  const disabledRef = page.getByTestId("flashpoint-utterance-ref");
  await expect(disabledRef).toHaveAttribute("aria-disabled", "true");
  await disabledRef.click();

  await expect(page.getByTestId("page-frame-iframe")).toBeVisible();
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Original" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
