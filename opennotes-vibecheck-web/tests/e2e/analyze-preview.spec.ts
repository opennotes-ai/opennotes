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

const PERMISSIVE_JOB_ID = "66666666-6666-7666-8666-666666666666";
const BLOCKED_JOB_ID = "77777777-7777-7777-8777-777777777777";
const ATTEMPT_ID = "88888888-8888-7888-8888-888888888888";
const SCREENSHOT_URL =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='960' height='640'%3E%3Crect width='960' height='640' fill='%23f8fafc'/%3E%3Ctext x='48' y='96' font-family='Arial' font-size='48' fill='%230f172a'%3EPreview fallback%3C/text%3E%3C/svg%3E";

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

function jobState(jobId: string) {
  const blocked = jobId === BLOCKED_JOB_ID;
  return {
    job_id: jobId,
    url: `${apiBaseUrl}/${blocked ? "blocked-page" : "permissive-page"}`,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-24T18:00:00Z",
    updated_at: "2026-04-24T18:00:01Z",
    sections: {},
    sidebar_payload: null,
    cached: false,
    next_poll_ms: 1500,
    page_title: "Preview fixture",
    page_kind: "article",
    utterance_count: 1,
  };
}

async function previewWidth(page: Page): Promise<number> {
  const box = await page.locator('[data-testid="page-frame-iframe"]').boundingBox();
  if (!box) throw new Error("preview iframe has no box");
  return box.width;
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${PERMISSIVE_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(PERMISSIVE_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${BLOCKED_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(BLOCKED_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      const blocked = targetUrl.includes("/blocked-page");
      writeJson(response, 200, {
        can_iframe: !blocked,
        blocking_header: blocked
          ? "content-security-policy: frame-ancestors 'none'"
          : null,
        csp_frame_ancestors: blocked ? "frame-ancestors 'none'" : null,
      });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/screenshot"
    ) {
      writeJson(response, 200, { screenshot_url: SCREENSHOT_URL });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/permissive-page") {
      response.writeHead(200, { "content-type": "text/html" });
      response.end("<!doctype html><h1>Permissive frame fixture</h1>");
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/blocked-page") {
      response.writeHead(200, {
        "content-security-policy": "frame-ancestors 'none'",
        "content-type": "text/html",
      });
      response.end("<!doctype html><h1>Blocked frame fixture</h1>");
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
  if (webProcess && !webProcess.killed) {
    webProcess.kill("SIGTERM");
  }
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test("preview size presets resize the frame and persist across reload", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${PERMISSIVE_JOB_ID}`);
  await expect(page.locator('[data-testid="page-frame-iframe"]')).toBeVisible();
  await expect(page.locator('[data-testid="page-frame-screenshot"]')).toHaveCount(0);

  const regularWidth = await previewWidth(page);
  await page.getByRole("button", { name: "Large" }).click();
  await expect(page.locator('[data-testid="analyze-layout"]')).toHaveAttribute(
    "data-preview-size",
    "large",
  );
  await expect
    .poll(async () => previewWidth(page))
    .toBeGreaterThan(regularWidth + 40);

  await page.reload();
  await expect(page.locator('[data-testid="analyze-layout"]')).toHaveAttribute(
    "data-preview-size",
    "large",
  );

  await page.getByRole("button", { name: "Max width" }).click();
  const previewBox = await page.locator('[aria-label="Page preview"]').boundingBox();
  const sidebarBox = await page.locator('[data-testid="analysis-sidebar"]').boundingBox();
  if (!previewBox || !sidebarBox) throw new Error("layout boxes were not available");
  expect(sidebarBox.y).toBeGreaterThan(previewBox.y + previewBox.height - 1);
});

test("CSP frame-ancestors blocks swap to screenshot within one second", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${BLOCKED_JOB_ID}`);
  await expect(page.locator('[data-testid="page-frame-screenshot"]')).toBeVisible({
    timeout: 1000,
  });
  await expect(page.locator('[data-testid="page-frame-iframe"]')).toHaveAttribute(
    "aria-hidden",
    "true",
  );
});
