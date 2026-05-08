import { expect, test, type Request as PwRequest } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { fileURLToPath } from "node:url";

const FEEDBACK_ID = "fb000000-0000-7000-8000-000000000001";
const ANALYSES = [
  {
    job_id: "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
    source_url: "https://example.com/feedback-fixture-1",
    page_title: "Feedback Fixture Article",
    screenshot_url: "https://placehold.co/800x600",
    preview_description: "A test article for feedback e2e.",
    headline_summary: null,
    weather_report: null,
    completed_at: "2026-01-01T00:00:00Z",
  },
];

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let setUidCookieOnOpenPost = false;
const patchUidHeaderObservations: string[] = [];

const FAKE_UID = "11111111-1111-7111-8111-111111111111";

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

async function readBody(request: IncomingMessage): Promise<string> {
  let body = "";
  for await (const chunk of request) {
    body += chunk.toString();
  }
  return body;
}

function writeJson(
  response: ServerResponse<IncomingMessage>,
  status: number,
  body: unknown,
): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    void (async () => {
      const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");

      if (
        request.method === "GET" &&
        requestUrl.pathname === "/api/analyses/recent"
      ) {
        writeJson(response, 200, ANALYSES);
        return;
      }

      if (
        request.method === "POST" &&
        requestUrl.pathname === "/api/feedback"
      ) {
        await readBody(request);
        const headers: Record<string, string | string[]> = {
          "content-type": "application/json",
        };
        if (setUidCookieOnOpenPost) {
          headers["set-cookie"] = [
            `VIBECHECK_UID=${FAKE_UID}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000`,
          ];
        }
        response.writeHead(201, headers);
        response.end(JSON.stringify({ id: FEEDBACK_ID }));
        return;
      }

      if (
        request.method === "PATCH" &&
        requestUrl.pathname === `/api/feedback/${FEEDBACK_ID}`
      ) {
        await readBody(request);
        const cookieHeader = request.headers.cookie ?? "";
        patchUidHeaderObservations.push(cookieHeader);
        writeJson(response, 200, {});
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
  if (webProcess && !webProcess.killed) {
    webProcess.kill("SIGTERM");
  }
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test("AC1: happy path — bell → popover → thumbs up → dialog → send → closes", async ({
  page,
}) => {
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });

  const section = page.locator('[data-testid="recently-vibe-checked"]');
  await expect(section).toBeVisible({ timeout: 10_000 });

  const bell = page
    .locator('[aria-label*="Send feedback about"]')
    .first();
  await expect(bell).toBeVisible({ timeout: 5_000 });

  await bell.hover();

  const thumbsUpBtn = page.locator('[aria-label="Thumbs up"]').first();
  const thumbsDownBtn = page.locator('[aria-label="Thumbs down"]').first();
  const messageBtn = page.locator('[aria-label="Send a message"]').first();

  await expect(thumbsUpBtn).toBeVisible({ timeout: 5_000 });
  await expect(thumbsDownBtn).toBeVisible({ timeout: 3_000 });
  await expect(messageBtn).toBeVisible({ timeout: 3_000 });

  const openResponsePromise = page.waitForResponse(
    (r) =>
      /\/api\/feedback$/.test(new URL(r.url()).pathname) &&
      r.request().method() === "POST",
    { timeout: 10_000 },
  );

  await thumbsUpBtn.click();

  const dialog = page.getByRole("dialog", { name: "Send feedback" });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  const thumbsUpToggle = dialog.locator('[aria-label="Thumbs up"]');
  await expect(thumbsUpToggle).toHaveAttribute("aria-pressed", "true", {
    timeout: 5_000,
  });

  await openResponsePromise;

  const patchPromise = page.waitForResponse(
    (r) =>
      /\/api\/feedback\/[^/]+$/.test(new URL(r.url()).pathname) &&
      r.request().method() === "PATCH",
    { timeout: 10_000 },
  );

  const sendButton = dialog.locator('button[type="submit"]');
  await expect(sendButton).toBeEnabled({ timeout: 3_000 });
  await sendButton.click();

  await patchPromise;

  await expect(dialog).toHaveCount(0, { timeout: 5_000 });
});

test("AC2: send-gating — message type requires 5+ chars", async ({ page }) => {
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });

  const section = page.locator('[data-testid="recently-vibe-checked"]');
  await expect(section).toBeVisible({ timeout: 10_000 });

  const bell = page
    .locator('[aria-label*="Send feedback about"]')
    .first();
  await bell.hover();

  const messageBtn = page.locator('[aria-label="Send a message"]').first();
  await expect(messageBtn).toBeVisible({ timeout: 5_000 });

  await messageBtn.click();

  const dialog = page.getByRole("dialog", { name: "Send feedback" });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  const messageToggle = dialog.locator('[aria-label="Send a message"]');
  await expect(messageToggle).toHaveAttribute("aria-pressed", "true", {
    timeout: 5_000,
  });

  const sendButton = dialog.locator('button[type="submit"]');
  await expect(sendButton).toBeDisabled({ timeout: 3_000 });

  const textarea = dialog.locator('textarea');
  await textarea.fill("abcd");
  await expect(sendButton).toBeDisabled({ timeout: 3_000 });

  await textarea.fill("abcde");
  await expect(sendButton).toBeEnabled({ timeout: 3_000 });

  const patchPromise = page.waitForResponse(
    (r) =>
      /\/api\/feedback\/[^/]+$/.test(new URL(r.url()).pathname) &&
      r.request().method() === "PATCH",
    { timeout: 10_000 },
  );

  await sendButton.click();

  await patchPromise;

  await expect(dialog).toHaveCount(0, { timeout: 5_000 });
});

test("AC3: open-POST failure triggers combined fallback POST on send", async ({
  page,
}) => {
  let openPostIntercepted = false;

  await page.route("**/api/feedback", async (route) => {
    const method = route.request().method();
    if (method === "POST" && !openPostIntercepted) {
      openPostIntercepted = true;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "forced" }),
      });
      return;
    }
    await route.continue();
  });

  const capturedRequests: Array<{ method: string; body: string }> = [];
  page.on("request", (req: PwRequest) => {
    if (
      /\/api\/feedback$/.test(new URL(req.url()).pathname) &&
      req.method() === "POST"
    ) {
      capturedRequests.push({ method: req.method(), body: req.postData() ?? "" });
    }
  });

  await page.goto(webBaseUrl, { waitUntil: "networkidle" });

  const section = page.locator('[data-testid="recently-vibe-checked"]');
  await expect(section).toBeVisible({ timeout: 10_000 });

  const bell = page
    .locator('[aria-label*="Send feedback about"]')
    .first();
  await bell.hover();

  const thumbsUpBtn = page.locator('[aria-label="Thumbs up"]').first();
  await expect(thumbsUpBtn).toBeVisible({ timeout: 5_000 });

  await thumbsUpBtn.click();

  const dialog = page.getByRole("dialog", { name: "Send feedback" });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  await expect(dialog.locator('[aria-label="Thumbs up"]')).toHaveAttribute(
    "aria-pressed",
    "true",
    { timeout: 5_000 },
  );

  const combinedPostPromise = page.waitForResponse(
    (r) =>
      /\/api\/feedback$/.test(new URL(r.url()).pathname) &&
      r.request().method() === "POST" &&
      r.status() !== 500,
    { timeout: 10_000 },
  );

  const sendButton = dialog.locator('button[type="submit"]');
  await expect(sendButton).toBeEnabled({ timeout: 3_000 });
  await sendButton.click();

  const combinedResponse = await combinedPostPromise;
  expect(combinedResponse.status()).not.toBe(500);

  expect(capturedRequests.length).toBeGreaterThanOrEqual(2);

  const combinedBody = capturedRequests[1];
  expect(combinedBody).toBeDefined();

  const parsed = JSON.parse(combinedBody.body) as Record<string, unknown>;
  expect(parsed).toHaveProperty("initial_type");
  expect(parsed).toHaveProperty("final_type");

  await expect(dialog).toHaveCount(0, { timeout: 5_000 });
});

test("AC4: Set-Cookie from open POST roundtrips and is sent on subsequent PATCH", async ({
  page,
  context,
}) => {
  setUidCookieOnOpenPost = true;
  patchUidHeaderObservations.length = 0;

  try {
    const cookiesBefore = await context.cookies();
    expect(
      cookiesBefore.some((c) => c.name === "VIBECHECK_UID"),
      "browser must start with no VIBECHECK_UID cookie",
    ).toBe(false);

    await page.goto(webBaseUrl, { waitUntil: "networkidle" });

    const section = page.locator('[data-testid="recently-vibe-checked"]');
    await expect(section).toBeVisible({ timeout: 10_000 });

    const bell = page
      .locator('[aria-label*="Send feedback about"]')
      .first();
    await bell.hover();

    const thumbsUpBtn = page.locator('[aria-label="Thumbs up"]').first();
    await expect(thumbsUpBtn).toBeVisible({ timeout: 5_000 });

    const openResponsePromise = page.waitForResponse(
      (r) =>
        /\/api\/feedback$/.test(new URL(r.url()).pathname) &&
        r.request().method() === "POST",
      { timeout: 10_000 },
    );

    await thumbsUpBtn.click();

    const dialog = page.getByRole("dialog", { name: "Send feedback" });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await openResponsePromise;

    await expect
      .poll(
        async () => {
          const cookies = await context.cookies();
          return cookies.find((c) => c.name === "VIBECHECK_UID")?.value;
        },
        { timeout: 5_000 },
      )
      .toBe(FAKE_UID);

    const patchPromise = page.waitForResponse(
      (r) =>
        /\/api\/feedback\/[^/]+$/.test(new URL(r.url()).pathname) &&
        r.request().method() === "PATCH",
      { timeout: 10_000 },
    );

    const sendButton = dialog.locator('button[type="submit"]');
    await expect(sendButton).toBeEnabled({ timeout: 3_000 });
    await sendButton.click();

    await patchPromise;

    expect(
      patchUidHeaderObservations.length,
      "fake server should have received at least one PATCH",
    ).toBeGreaterThan(0);
    const observed = patchUidHeaderObservations[0];
    expect(
      observed.includes(`VIBECHECK_UID=${FAKE_UID}`),
      `expected upstream PATCH cookie header to include VIBECHECK_UID=${FAKE_UID}, got: ${observed}`,
    ).toBe(true);

    await expect(dialog).toHaveCount(0, { timeout: 5_000 });
  } finally {
    setUidCookieOnOpenPost = false;
    await context.clearCookies();
  }
});
