import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";

const FIXTURE_ANALYSES = [
  {
    job_id: "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
    source_url: "https://example.com/article-1",
    page_title: "Example Article 1",
    screenshot_url: "https://placehold.co/800x600",
    preview_description: "A short blurb about article 1.",
    completed_at: "2026-01-01T00:00:00Z",
  },
  {
    job_id: "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
    source_url: "https://example.com/article-2",
    page_title: "Example Article 2",
    screenshot_url: "https://placehold.co/800x600",
    preview_description: "A short blurb about article 2.",
    completed_at: "2026-01-02T00:00:00Z",
  },
  {
    job_id: "cccccccc-cccc-7ccc-8ccc-cccccccccccc",
    source_url: "https://example.com/article-3",
    page_title: "Example Article 3",
    screenshot_url: "https://placehold.co/800x600",
    preview_description: "A short blurb about article 3.",
    completed_at: "2026-01-03T00:00:00Z",
  },
  {
    job_id: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
    source_url: "https://example.com/article-4",
    page_title: "Example Article 4",
    screenshot_url: "https://placehold.co/800x600",
    preview_description: "A short blurb about article 4.",
    completed_at: "2026-01-04T00:00:00Z",
  },
  {
    job_id: "eeeeeeee-eeee-7eee-8eee-eeeeeeeeeeee",
    source_url: "https://example.com/article-5",
    page_title: "Example Article 5",
    screenshot_url: "https://placehold.co/800x600",
    preview_description: "A short blurb about article 5.",
    completed_at: "2026-01-05T00:00:00Z",
  },
];

let mockMode: "normal" | "empty" | "error" = "normal";

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

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/analyses/recent"
    ) {
      if (mockMode === "error") {
        response.writeHead(500, { "content-type": "application/json" });
        response.end(JSON.stringify({ error_code: "internal_error" }));
        return;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify(mockMode === "empty" ? [] : FIXTURE_ANALYSES),
      );
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
  mockMode = "normal";
});

test("5 cards render on home page", async ({ page }) => {
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });
  const section = page.locator('[data-testid="recently-vibe-checked"]');
  await expect(section).toBeVisible({ timeout: 10_000 });
  const cards = section.locator('[data-testid="recent-analysis-card"]');
  await expect(cards).toHaveCount(5);
  await expect(section).toContainText("Example Article 1");
});

test("card href navigates to /analyze?job=<id>", async ({ page }) => {
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });
  const section = page.locator('[data-testid="recently-vibe-checked"]');
  await expect(section).toBeVisible({ timeout: 10_000 });
  const firstCard = section
    .locator('[data-testid="recent-analysis-card"]')
    .first();
  await firstCard.click();
  await page.waitForURL(
    (url) =>
      url.pathname === "/analyze" &&
      url.searchParams.get("job") ===
        "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
    { timeout: 10_000 },
  );
});

test("empty fixture: no gallery section rendered", async ({ page }) => {
  mockMode = "empty";
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });
  await expect(
    page.locator('[data-testid="recently-vibe-checked"]'),
  ).toHaveCount(0);
});

test("API error: no gallery section rendered", async ({ page }) => {
  mockMode = "error";
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });
  await expect(
    page.locator('[data-testid="recently-vibe-checked"]'),
  ).toHaveCount(0);
});
