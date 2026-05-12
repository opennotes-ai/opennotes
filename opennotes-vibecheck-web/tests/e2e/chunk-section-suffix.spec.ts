import { expect, test } from "@playwright/test";
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

const JOB_ID = "11111111-1111-7111-8111-111111111111";
const ATTEMPT_ID = "22222222-2222-7222-8222-222222222222";
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

function jobState() {
  return {
    job_id: JOB_ID,
    url: `${apiBaseUrl}/chunked-source`,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-12T16:00:00Z",
    updated_at: "2026-05-12T16:00:01Z",
    sections: {},
    sidebar_payload: {
      headline: null,
      utterances: [
        { position: 1, utterance_id: "post-legacy" },
        { position: 2, utterance_id: "post-chunked" },
      ],
      safety: {
        recommendation: null,
        harmful_content_matches: [
          {
            utterance_id: "post-legacy",
            utterance_text: "Legacy single section match.",
            max_score: 0.81,
            flagged_categories: ["harassment"],
            categories: { harassment: true },
            scores: { harassment: 0.81 },
            source: "openai",
          },
          {
            utterance_id: "post-chunked",
            utterance_text: "Chunked aggregate match.",
            max_score: 0.95,
            flagged_categories: ["harassment"],
            categories: { harassment: true },
            scores: { harassment: 0.95 },
            source: "openai",
            chunk_idx: null,
            chunk_count: 3,
          },
          {
            utterance_id: "post-chunked",
            utterance_text: "Chunk one match.",
            max_score: 0.91,
            flagged_categories: ["harassment"],
            categories: { harassment: true },
            scores: { harassment: 0.91 },
            source: "openai",
            chunk_idx: 0,
            chunk_count: 3,
          },
        ],
      },
      web_risk: { findings: [] },
      image_moderation: { matches: [] },
      video_moderation: { matches: [] },
      facts_claims: {
        claims_report: {
          deduped_claims: [
            {
              canonical_text: "A chunked factual claim appears.",
              occurrence_count: 1,
              author_count: 1,
              utterance_ids: ["post-chunked"],
              category: "potentially_factual",
              chunk_refs: [
                {
                  utterance_id: "post-chunked",
                  chunk_idx: 2,
                  chunk_count: 3,
                },
              ],
            },
            {
              canonical_text: "A legacy factual claim appears.",
              occurrence_count: 1,
              author_count: 1,
              utterance_ids: ["post-legacy"],
              category: "potentially_factual",
            },
          ],
          total_claims: 2,
          total_unique: 2,
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
              utterance_id: "post-chunked",
              claim_text: "The chunked source is unfair.",
              stance: "opposes",
              chunk_idx: 1,
              chunk_count: 3,
            },
          ],
        },
      },
      tone_dynamics: { flashpoint_matches: [] },
    },
    cached: false,
    next_poll_ms: 1500,
    page_title: "Chunk suffix fixture",
    page_kind: "article",
    utterance_count: 2,
  };
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (request.method === "GET" && requestUrl.pathname === `/api/analyze/${JOB_ID}`) {
      writeJson(response, 200, jobState());
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/frame-compat") {
      writeJson(response, 200, {
        can_iframe: true,
        blocking_header: null,
        csp_frame_ancestors: null,
        has_archive: false,
      });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
      writeJson(response, 200, { screenshot_url: SCREENSHOT_URL });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/chunked-source") {
      response.writeHead(200, { "content-type": "text/html" });
      response.end("<!doctype html><h1>Chunked source fixture</h1>");
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

test("renders section suffixes for chunked report refs and omits them for legacy refs", async ({
  page,
}, testInfo) => {
  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`);
  await expect(page.getByTestId("analysis-sidebar")).toBeVisible();

  await expect(page.getByTestId("safety-count")).toHaveText("2 flagged");
  await expect(
    page.getByTestId("safety-utterance-ref").filter({ hasText: /^post #1$/ }),
  ).toHaveCount(1);
  await expect(
    page.getByTestId("safety-utterance-ref").filter({ hasText: /^post #2$/ }),
  ).toHaveCount(1);
  await page.getByTestId("safety-chunk-details").locator("summary").click();
  await expect(
    page.getByTestId("safety-utterance-ref").filter({ hasText: /^post #2 §1$/ }),
  ).toHaveCount(1);
  await expect(page.getByTestId("subjective-claim-utterance-ref")).toHaveText("post #2 §2");
  await expect(page.getByTestId("deduped-claim-utterance-ref").first()).toHaveText("post #2 §3");
  await expect(page.getByTestId("deduped-claim-utterance-ref").nth(1)).toHaveText("post #1");

  await testInfo.attach("chunk-section-suffix", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});
