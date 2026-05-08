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
import { stopWebProcess } from "./_helpers/web-process";

const PERMISSIVE_JOB_ID = "66666666-6666-7666-8666-666666666666";
const BLOCKED_WITH_ARCHIVE_JOB_ID = "77777777-7777-7777-8777-777777777777";
const BLOCKED_WITHOUT_ARCHIVE_JOB_ID = "99999999-9999-7999-8999-999999999999";
const ARCHIVE_FAIL_JOB_ID = "11111111-1111-7111-8111-111111111111";
const ARCHIVE_DELAYED_JOB_ID = "55555555-5555-7555-8555-555555555555";
const ATTEMPT_ID = "88888888-8888-7888-8888-888888888888";
const SCREENSHOT_URL =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='2560' height='1800'%3E%3Crect width='2560' height='1800' fill='%23f8fafc'/%3E%3Ctext x='80' y='160' font-family='Arial' font-size='72' fill='%230f172a'%3EWide preview fallback%3C/text%3E%3C/svg%3E";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const configuredPollAttempts = Number.parseInt(
  process.env.ANALYZE_PREVIEW_POLL_ATTEMPTS ?? "14",
  10,
);
const MAX_PREVIEW_POLL_ATTEMPTS = Number.isFinite(configuredPollAttempts)
  ? Math.min(Math.max(configuredPollAttempts, 1), 14)
  : 14;
const PREVIEW_POLL_INTERVAL_MS = 1_250;

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

function jobState(jobId: string) {
  let path = "permissive-page";
  if (jobId === BLOCKED_WITH_ARCHIVE_JOB_ID) path = "blocked-page";
  else if (jobId === BLOCKED_WITHOUT_ARCHIVE_JOB_ID) path = "blocked-no-archive-page";
  else if (jobId === ARCHIVE_FAIL_JOB_ID) path = "archive-fail-page";
  else if (jobId === ARCHIVE_DELAYED_JOB_ID) path = "archive-delayed-page";
  return {
    job_id: jobId,
    url: `${apiBaseUrl}/${path}`,
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
  const box = await page.getByTestId("page-frame-iframe").boundingBox();
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
      requestUrl.pathname === `/api/analyze/${BLOCKED_WITH_ARCHIVE_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(BLOCKED_WITH_ARCHIVE_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${BLOCKED_WITHOUT_ARCHIVE_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(BLOCKED_WITHOUT_ARCHIVE_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${ARCHIVE_FAIL_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(ARCHIVE_FAIL_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${ARCHIVE_DELAYED_JOB_ID}`
    ) {
      writeJson(response, 200, jobState(ARCHIVE_DELAYED_JOB_ID));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      const blocked =
        targetUrl.includes("/blocked-page") ||
        targetUrl.includes("/blocked-no-archive-page") ||
        targetUrl.includes("/archive-fail-page") ||
        targetUrl.includes("/archive-delayed-page");
      const hasArchive =
        targetUrl.includes("/blocked-page") ||
        targetUrl.includes("/archive-fail-page") ||
        targetUrl.includes("/archive-delayed-page");
      writeJson(response, 200, {
        can_iframe: !blocked,
        blocking_header: blocked
          ? "content-security-policy: frame-ancestors 'none'"
          : null,
        csp_frame_ancestors: blocked ? "frame-ancestors 'none'" : null,
        has_archive: hasArchive,
      });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/archive-preview"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      if (targetUrl.includes("/blocked-page")) {
        response.writeHead(200, {
          "cache-control": "no-store, private",
          "content-security-policy":
            "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
          "content-type": "text/html; charset=utf-8",
        });
        response.end("<!doctype html><h1>Archived preview fixture</h1>");
        return;
      }
      if (targetUrl.includes("/archive-delayed-page")) {
        const timer = setTimeout(() => {
          response.writeHead(200, {
            "cache-control": "no-store, private",
            "content-security-policy":
              "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
            "content-type": "text/html; charset=utf-8",
          });
          response.end("<!doctype html><h1>Archived preview fixture</h1>");
        }, 3_000);
        timer.unref?.();
        return;
      }
      if (targetUrl.includes("/archive-fail-page")) {
        response.writeHead(502, {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "no-store, private",
        });
        response.end("Archive unavailable");
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
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/blocked-no-archive-page"
    ) {
      response.writeHead(200, {
        "content-security-policy": "frame-ancestors 'none'",
        "content-type": "text/html",
      });
      response.end("<!doctype html><h1>Blocked no archive fixture</h1>");
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/archive-fail-page"
    ) {
      response.writeHead(200, {
        "content-security-policy": "frame-ancestors 'none'",
        "content-type": "text/html",
      });
      response.end("<!doctype html><h1>Archive fail fixture</h1>");
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/archive-delayed-page"
    ) {
      response.writeHead(200, {
        "content-security-policy": "frame-ancestors 'none'",
        "content-type": "text/html",
      });
      response.end("<!doctype html><h1>Archive delayed fixture</h1>");
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

test("preview size presets resize the frame and persist across reload", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${PERMISSIVE_JOB_ID}`);
  await expect(page.getByTestId("page-frame-iframe")).toBeVisible();
  await expect(page.getByTestId("page-frame-screenshot")).toHaveCount(0);

  const regularWidth = await previewWidth(page);
  await page.getByRole("button", { name: "Large" }).click();
  await expect(page.getByTestId("analyze-layout")).toHaveAttribute(
    "data-preview-size",
    "large",
  );
  await expect
    .poll(async () => previewWidth(page))
    .toBeGreaterThan(regularWidth + 40);

  await page.reload();
  await expect(page.getByTestId("analyze-layout")).toHaveAttribute(
    "data-preview-size",
    "large",
  );

  await page.getByRole("button", { name: "Max width" }).click();
  const previewBox = await page.locator('[aria-label="Page preview"]').boundingBox();
  const sidebarBox = await page.getByTestId("analysis-sidebar").boundingBox();
  if (!previewBox || !sidebarBox) throw new Error("layout boxes were not available");
  expect(sidebarBox.y).toBeGreaterThan(previewBox.y + previewBox.height - 1);
});

test("permissive page keeps the original iframe by default", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${PERMISSIVE_JOB_ID}`);
  await expect(page.getByTestId("page-frame-iframe")).toBeVisible();
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveCount(0);
  await expect(page.getByTestId("page-frame-screenshot")).toHaveCount(0);
});

test("CSP frame-ancestors auto-resolves to archive immediately, no countdown (TASK-1483.13.02)", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${BLOCKED_WITH_ARCHIVE_JOB_ID}`);

  // Server reports blocked → skip the deciding interstitial entirely and
  // resolve straight to archive.
  await expect(
    page.getByTestId("page-frame-archived-iframe"),
  ).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(
    0,
  );
  await expect(
    page.getByTestId("page-frame-archived-iframe"),
  ).toHaveAttribute("sandbox", "allow-same-origin");

  // Tab press follows the auto-resolved mode.
  await expect(
    page.getByRole("button", { name: "Archived" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: "Original" }),
  ).toHaveAttribute("aria-pressed", "false");

  // Original tab is hard-disabled (disabled attribute set, aria-describedby tooltip).
  const original = page.getByTestId("preview-mode-original");
  await expect(original).toHaveAttribute(
    "aria-describedby",
    "preview-mode-original-tip",
  );
  await expect(original).toBeDisabled();

  const archivedText = page
    .getByTestId("page-frame-archived-iframe")
    .contentFrame()
    .locator("h1");
  await expect(archivedText).toHaveText("Archived preview fixture");
});

test("CSP frame-ancestors auto-resolves to screenshot when no archive is available (TASK-1483.13.02)", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${BLOCKED_WITHOUT_ARCHIVE_JOB_ID}`);

  await expect(
    page.getByTestId("page-frame-screenshot"),
  ).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(
    0,
  );

  await expect(
    page.getByRole("button", { name: "Screenshot" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: "Original" }),
  ).toHaveAttribute("aria-pressed", "false");
});

test("manual preview mode clicks switch visible previews (TASK-1483.13.02)", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${BLOCKED_WITH_ARCHIVE_JOB_ID}`);
  await expect(page.getByTestId("preview-mode-selector")).toBeVisible();
  await expect(page.getByTestId("preview-size-selector")).toBeVisible();

  // Initial render auto-resolves to Archived (no deciding).
  await expect(
    page.getByTestId("page-frame-archived-iframe"),
  ).toBeVisible();
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(
    0,
  );

  await page.getByRole("button", { name: "Screenshot" }).click();
  await expect(
    page.getByTestId("page-frame-screenshot"),
  ).toBeVisible();

  await page.getByRole("button", { name: "Archived" }).click();
  await expect(
    page.getByTestId("page-frame-archived-iframe"),
  ).toBeVisible();

  // Original is hard-disabled (TASK-1591.02) — force-clicking is a noop.
  await page.getByTestId("preview-mode-original").click({ force: true });
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(0);
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible();

  // Width-preset assertion uses the section, not a possibly-hidden iframe.
  const sectionWidth = async () => {
    const box = await page.locator('[aria-label="Page preview"]').boundingBox();
    if (!box) throw new Error("preview section has no box");
    return box.width;
  };
  const regularWidth = await sectionWidth();
  await page.getByRole("button", { name: "Large" }).click();
  await expect.poll(async () => sectionWidth()).toBeGreaterThan(regularWidth + 40);
});

test("archive 502 onError fires; auto-switch lands on Screenshot (AC #6 e2e)", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${ARCHIVE_FAIL_JOB_ID}`);

  // Server reports blocked → PageFrame attempts the archive iframe immediately
  // (no deciding). The archive returns 502 + text/plain, so iframe.onError
  // fires; chain B then resolves to screenshot.
  await expect(
    page.getByTestId("page-frame-screenshot"),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "Screenshot" }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("tab aria-pressed is correct after auto-resolution; Original disabled and never becomes pressed (TASK-1483.13.02)", async ({
  page,
}) => {
  await page.goto(`${webBaseUrl}/analyze?job=${BLOCKED_WITH_ARCHIVE_JOB_ID}`);
  // Auto-resolves to Archived. Original is hard-disabled (TASK-1591.02).
  await expect(
    page.getByTestId("page-frame-archived-iframe"),
  ).toBeVisible({ timeout: 5_000 });

  await expect(
    page.getByRole("button", { name: "Archived" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: "Original" }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("preview-mode-original")).toBeDisabled();

  // Force-clicking disabled Original must not change pressed state.
  await page.getByTestId("preview-mode-original").click({ force: true });
  await expect(
    page.getByRole("button", { name: "Archived" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: "Original" }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(
    page.getByTestId("page-frame-archived-iframe"),
  ).toBeVisible({ timeout: 5_000 });
});

test("wide screenshot scrolls inside the section, never expands the layout (containment)", async ({
  page,
}) => {
  // PERMISSIVE_JOB_ID fixture renders successfully — switch to Screenshot tab
  // to display the wide SCREENSHOT_URL fixture inside the section.
  await page.goto(`${webBaseUrl}/analyze?job=${PERMISSIVE_JOB_ID}`);
  await page.getByRole("button", { name: "Screenshot" }).click();
  await expect(page.getByTestId("page-frame-screenshot")).toBeVisible();

  // The <section aria-label="Page preview"> has overflow-hidden so its
  // scrollWidth === clientWidth. The actual scroll container is the div
  // wrapper around the screenshot img (PageFrame.tsx, overflow-auto). Target
  // that wrapper directly via the screenshot's parent element.
  const wrapperMetrics = await page
    .getByTestId("page-frame-screenshot")
    .evaluate((img: Element) => {
      const parent = (img as HTMLElement).parentElement as HTMLElement;
      return {
        scrollWidth: parent.scrollWidth,
        clientWidth: parent.clientWidth,
        scrollHeight: parent.scrollHeight,
        clientHeight: parent.clientHeight,
      };
    });

  // Wrapper's scrollable inner content (the wide screenshot) is wider than
  // its visible viewport — horizontal scroll exists *inside* the wrapper.
  expect(wrapperMetrics.scrollWidth).toBeGreaterThan(wrapperMetrics.clientWidth);

  // Outer layout MUST NOT overflow — analyze-layout's scroll dims equal client dims.
  const layout = page.getByTestId("analyze-layout");
  const layoutMetrics = await layout.evaluate((el: Element) => ({
    scrollWidth: (el as HTMLElement).scrollWidth,
    clientWidth: (el as HTMLElement).clientWidth,
  }));
  expect(layoutMetrics.scrollWidth).toBe(layoutMetrics.clientWidth);
});

test("archived tab shows loading overlay while archive fetch is in flight (TASK-1591.01)", async ({ page }) => {
  await page.goto(`${webBaseUrl}/analyze?job=${ARCHIVE_DELAYED_JOB_ID}`, { waitUntil: "domcontentloaded" });

  // Loading overlay must appear before the archived iframe paints content.
  await expect(page.getByTestId("page-frame-archived-loading")).toBeVisible({ timeout: 8_000 });
  await expect(page.getByTestId("page-frame-archived-loading")).toContainText("Loading archived version");

  // Once the delayed response lands and the iframe load handler classifies it
  // as rendered, the overlay disappears and the iframe content is shown.
  await expect(page.getByTestId("page-frame-archived-loading")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible();
  const archivedText = page
    .getByTestId("page-frame-archived-iframe")
    .contentFrame()
    .locator("h1");
  await expect(archivedText).toHaveText("Archived preview fixture");
});

test("Original tab is disabled when canIframe=false; click is a noop; tooltip shows (TASK-1591.02)", async ({ page }) => {
  await page.goto(`${webBaseUrl}/analyze?job=${BLOCKED_WITH_ARCHIVE_JOB_ID}`);

  // Auto-resolves to Archived (existing behavior).
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible({ timeout: 5_000 });
  const original = page.getByTestId("preview-mode-original");
  await expect(original).toBeDisabled();

  // Capture which tab is currently pressed (Archived in this fixture).
  const archivedPressedBefore = await page
    .getByRole("button", { name: "Archived" })
    .getAttribute("aria-pressed");
  expect(archivedPressedBefore).toBe("true");

  // Force-click the disabled Original button — must not change resolved mode.
  await original.click({ force: true });
  await expect(page.getByRole("button", { name: "Archived" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Original" })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible();

  // Hover the wrapper span (not the disabled button itself) — disabled buttons
  // do not fire pointer events reliably in Firefox/Safari (TASK-1591.04).
  const wrapper = page.getByTestId("preview-mode-original-hover-wrapper");
  const tip = page.getByTestId("preview-mode-original-tip");
  // Move mouse away first to ensure tooltip is in hidden state before hover test.
  await page.mouse.move(0, 0);
  await expect(tip).toHaveAttribute("data-visible", "false");
  await wrapper.hover();
  await expect(tip).toHaveAttribute("data-visible", "true");
  await expect(tip).toBeVisible();
  await expect(tip).toContainText("Original not available");
  await page.mouse.move(0, 0);
  await expect(tip).toHaveAttribute("data-visible", "false");
});
