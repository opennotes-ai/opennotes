import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";

const FAILED_JOB_ID = "15301530-1530-7530-8530-153015301530";
const RETRY_JOB_ID = "15301530-1530-7530-8530-153015301531";
const SOURCE_URL = "https://www.reddit.com/r/opennotes/comments/retry-cache/";
const ATTEMPT_ID = "aaaaaaaa-1530-7530-8530-aaaaaaaa1530";

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let analyzePostBodies: Array<{ url?: string }> = [];
let apiRequests: string[] = [];

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
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : null;
}

function writeJson(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function failedJobState(): Record<string, unknown> {
  return {
    job_id: FAILED_JOB_ID,
    status: "failed",
    url: SOURCE_URL,
    normalized_url: SOURCE_URL,
    source_type: "url",
    error_code: "timeout",
    error_message: "analysis timed out",
    cached: false,
    sections: {},
    sidebar_payload: null,
    sidebar_payload_complete: false,
    next_poll_ms: 1500,
    page_title: "Cached Reddit discussion",
    page_kind: "article",
    utterance_count: 0,
  };
}

function doneJobState(): Record<string, unknown> {
  return {
    job_id: RETRY_JOB_ID,
    status: "done",
    url: SOURCE_URL,
    normalized_url: SOURCE_URL,
    source_type: "url",
    cached: false,
    sections: {},
    sidebar_payload: null,
    sidebar_payload_complete: true,
    next_poll_ms: 1500,
    page_title: "Cached Reddit discussion",
    page_kind: "article",
    utterance_count: 0,
    attempt_id: ATTEMPT_ID,
  };
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    void (async () => {
      const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
      apiRequests.push(`${request.method ?? "GET"} ${requestUrl.pathname}`);

      if (request.method === "POST" && requestUrl.pathname === "/api/analyze") {
        const body = (await readJsonBody(request)) as { url?: string };
        analyzePostBodies.push(body);
        writeJson(response, 202, {
          job_id: RETRY_JOB_ID,
          status: "pending",
          cached: false,
        });
        return;
      }

      if (
        request.method === "GET" &&
        requestUrl.pathname === `/api/analyze/${FAILED_JOB_ID}`
      ) {
        writeJson(response, 200, failedJobState());
        return;
      }

      if (
        request.method === "GET" &&
        requestUrl.pathname === `/api/analyze/${RETRY_JOB_ID}`
      ) {
        writeJson(response, 200, doneJobState());
        return;
      }

      if (
        request.method === "GET" &&
        requestUrl.pathname === "/api/frame-compat"
      ) {
        writeJson(response, 200, { can_iframe: true, blocking_header: null });
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
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
  if (webProcess) {
    await stopWebProcess(webProcess);
  }
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test.beforeEach(() => {
  analyzePostBodies = [];
  apiRequests = [];
});

test("Try Again on a timed-out job submits the same URL and reaches a terminal retry", async ({
  page,
}) => {
  test.setTimeout(90_000);

  await page.goto(`${webBaseUrl}/analyze?job=${FAILED_JOB_ID}`);

  const failureCard = page.locator('[data-testid="job-failure-card"]');
  await expect(failureCard).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="job-failure-try-again"]')).toBeVisible();

  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("job") === RETRY_JOB_ID),
    page.locator('[data-testid="job-failure-try-again"]').click(),
  ]);

  await expect
    .poll(
      () =>
        apiRequests.filter(
          (request) => request === `GET /api/analyze/${RETRY_JOB_ID}`,
        ).length,
      { timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  expect(analyzePostBodies).toEqual([{ url: SOURCE_URL }]);
  expect(apiRequests).toContain(`GET /api/analyze/${FAILED_JOB_ID}`);
  expect(apiRequests).toContain("POST /api/analyze");
  expect(apiRequests).toContain(`GET /api/analyze/${RETRY_JOB_ID}`);
});
