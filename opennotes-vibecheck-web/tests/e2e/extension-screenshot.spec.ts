import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";

const JOB_ID = "33333333-3333-7333-8333-333333333333";
const ATTEMPT_ID = "44444444-4444-7444-8444-444444444444";
const SOURCE_URL = "https://example.com/extension-screenshot";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let scrapePayload: unknown = null;

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

function writeJson(
  response: ServerResponse<IncomingMessage>,
  status: number,
  body: unknown,
): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function completedJobState() {
  return {
    job_id: JOB_ID,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-05T08:00:00Z",
    updated_at: "2026-05-05T08:00:01Z",
    sections: {},
    sidebar_payload: null,
    cached: false,
    next_poll_ms: 1500,
    page_title: "Extension screenshot fixture",
    page_kind: "article",
    utterance_count: 1,
  };
}

async function readRequestBody(request: IncomingMessage): Promise<string> {
  let body = "";
  for await (const chunk of request) {
    body += chunk.toString();
  }
  return body;
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    void (async () => {
      const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
      if (request.method === "POST" && requestUrl.pathname === "/api/scrape") {
        scrapePayload = JSON.parse(await readRequestBody(request));
        writeJson(response, 201, {
          job_id: JOB_ID,
          analyze_url: `${webBaseUrl}/analyze?job=${JOB_ID}`,
          created_at: "2026-05-05T08:00:00Z",
        });
        return;
      }
      if (request.method === "GET" && requestUrl.pathname === `/api/analyze/${JOB_ID}`) {
        writeJson(response, 200, completedJobState());
        return;
      }
      if (request.method === "GET" && requestUrl.pathname === "/api/frame-compat") {
        writeJson(response, 200, {
          can_iframe: false,
          blocking_header: "content-security-policy",
          has_archive: true,
          archived_preview_url: `/api/archive-preview?url=${encodeURIComponent(
            SOURCE_URL,
          )}&job_id=${JOB_ID}`,
        });
        return;
      }
      if (request.method === "GET" && requestUrl.pathname === "/api/archive-preview") {
        response.writeHead(200, { "content-type": "text/html" });
        response.end(
          "<!doctype html><html><body><h1>Extension screenshot archive</h1></body></html>",
        );
        return;
      }
      if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
        writeJson(response, 200, { screenshot_url: null });
        return;
      }
      writeJson(response, 404, { error_code: "not_found" });
    })().catch((error) => {
      response.writeHead(500, { "content-type": "text/plain" });
      response.end(error instanceof Error ? error.message : String(error));
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

test("extension scrape submission carries screenshot and analyze page renders Archived frame", async ({
  page,
}) => {
  const screenshotBase64 = "iVBORw0KGgo=";
  const response = await fetch(`${apiBaseUrl}/api/scrape`, {
    method: "POST",
    headers: {
      authorization: "Bearer test",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      url: SOURCE_URL,
      html: "<html><body>Captured page</body></html>",
      screenshot_base64: screenshotBase64,
    }),
  });

  expect(response.status).toBe(201);
  expect(scrapePayload).toMatchObject({ screenshot_base64: screenshotBase64 });

  await page.goto(`${webBaseUrl}/analyze?job=${JOB_ID}`);
  await expect(page.getByRole("button", { name: "Archived" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible();
  await expect(
    page
      .getByTestId("page-frame-archived-iframe")
      .contentFrame()
      .locator("h1"),
  ).toHaveText("Extension screenshot archive");
});
