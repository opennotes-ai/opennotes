import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { readFileSync } from "node:fs";
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";

const ARCHIVE_IMAGE_JOB_ID = "15360000-0002-7000-8000-000000000002";
const DEFENSIVE_STYLES =
  "<style>img,video,iframe{max-width:100%;height:auto}</style>";
const ATTEMPT_ID = "15360000-9999-7000-8000-000000000999";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const FIXTURE_ROOT = fileURLToPath(new URL("../fixtures/", import.meta.url));
const CSS_URL = "https://archive-fixture.test/archive-css-images.css";

const archiveHtml = readFileSync(
  `${FIXTURE_ROOT}/archive-css-images.html`,
  "utf8",
).replace("__ARCHIVE_CSS_URL__", CSS_URL);
const archiveCss = readFileSync(
  `${FIXTURE_ROOT}/archive-css-images.css`,
  "utf8",
);

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

function writeJson(
  response: ServerResponse<IncomingMessage>,
  status: number,
  body: unknown,
): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function jobState(): Record<string, unknown> {
  return {
    job_id: ARCHIVE_IMAGE_JOB_ID,
    url: `${apiBaseUrl}/archive-css-images-source`,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-06T17:00:00Z",
    updated_at: "2026-05-06T17:00:01Z",
    sections: {},
    sidebar_payload: null,
    cached: false,
    next_poll_ms: 1500,
    page_title: "Archive CSS image sizing fixture",
    page_kind: "article",
    utterance_count: 0,
  };
}

async function imageSize(page: Page, selector: string) {
  const image = page
    .frameLocator('[data-testid="page-frame-archived-iframe"]')
    .locator(selector);
  await expect(image).toBeVisible();
  const box = await image.boundingBox();
  if (!box) throw new Error(`${selector} has no bounding box`);
  return { width: box.width, height: box.height };
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${ARCHIVE_IMAGE_JOB_ID}`
    ) {
      writeJson(response, 200, jobState());
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      writeJson(response, 200, {
        can_iframe: false,
        blocking_header: "content-security-policy: frame-ancestors 'none'",
        csp_frame_ancestors: "frame-ancestors 'none'",
        has_archive: true,
      });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/archive-preview"
    ) {
      response.writeHead(200, {
        "cache-control": "no-store, private",
        "content-type": "text/html; charset=utf-8",
      });
      response.end(DEFENSIVE_STYLES + archiveHtml);
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
      writeJson(response, 200, { screenshot_url: null });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/archive-css-images-source"
    ) {
      response.writeHead(200, {
        "content-security-policy": "frame-ancestors 'none'",
        "content-type": "text/html; charset=utf-8",
      });
      response.end("<!doctype html><h1>Blocked source fixture</h1>");
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

test("archive iframe preserves CSS-set image dimensions", async ({ page }) => {
  await page.route(CSS_URL, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/css; charset=utf-8",
      body: archiveCss,
    });
  });

  await page.goto(`${webBaseUrl}/analyze?job=${ARCHIVE_IMAGE_JOB_ID}`);
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible({
    timeout: 10_000,
  });

  await expect
    .poll(async () => imageSize(page, '[data-fixture-image="external"]'))
    .toEqual({ width: 200, height: 150 });
  await expect
    .poll(async () => imageSize(page, '[data-fixture-image="inline"]'))
    .toEqual({ width: 300, height: 200 });
});

test("defensive stylesheet caps intrinsically-sized images to iframe width", async ({ page }) => {
  await page.route(CSS_URL, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/css; charset=utf-8",
      body: archiveCss,
    });
  });

  await page.goto(`${webBaseUrl}/analyze?job=${ARCHIVE_IMAGE_JOB_ID}`);
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible({
    timeout: 10_000,
  });

  const iframeBox = await page.getByTestId("page-frame-archived-iframe").boundingBox();
  if (!iframeBox) throw new Error("iframe has no bounding box");

  await expect
    .poll(async () => {
      const size = await imageSize(page, '[data-fixture-image="intrinsic"]');
      return size.width;
    })
    .toBeLessThanOrEqual(iframeBox.width);
});
