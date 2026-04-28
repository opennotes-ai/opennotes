import { expect, test, type Page } from "@playwright/test";
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

const MID_POLL_JOB_ID = "14831503-0001-7000-8000-000000000001";
const TERMINAL_GRACE_JOB_ID = "14831503-0002-7000-8000-000000000002";
const CAP_JOB_ID = "14831503-0003-7000-8000-000000000003";
const TRANSIENT_JOB_ID = "14831503-0004-7000-8000-000000000004";
const FALLBACK_JOB_ID = "14831503-0005-7000-8000-000000000005";
const ATTEMPT_ID = "14831503-9999-7000-8000-000000000999";
const SCREENSHOT_URL =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='800'%3E%3Crect width='1200' height='800' fill='%23f8fafc'/%3E%3Ctext x='80' y='140' font-family='Arial' font-size='56' fill='%230f172a'%3EArchive staleness screenshot%3C/text%3E%3C/svg%3E";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PROBE_POLL_TIMEOUT_MS = 10_000;

type FixtureKind =
  | "mid-poll"
  | "terminal-grace"
  | "cap"
  | "transient"
  | "fallback";

const FIXTURES = new Map<string, FixtureKind>([
  [MID_POLL_JOB_ID, "mid-poll"],
  [TERMINAL_GRACE_JOB_ID, "terminal-grace"],
  [CAP_JOB_ID, "cap"],
  [TRANSIENT_JOB_ID, "transient"],
  [FALLBACK_JOB_ID, "fallback"],
]);

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let analyzeCalls = new Map<string, number>();
let frameCompatCalls = new Map<string, number>();

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

function fixturePath(kind: FixtureKind): string {
  return `/fixture/${kind}`;
}

function fixtureKindFromUrl(targetUrl: string): FixtureKind | null {
  for (const kind of FIXTURES.values()) {
    if (targetUrl.includes(fixturePath(kind))) return kind;
  }
  return null;
}

function jobState(jobId: string): Record<string, unknown> {
  const kind = FIXTURES.get(jobId);
  if (!kind) throw new Error(`unknown job id ${jobId}`);

  const count = (analyzeCalls.get(jobId) ?? 0) + 1;
  analyzeCalls.set(jobId, count);
  const status =
    kind === "terminal-grace" && count >= 2 ? "done" : "analyzing";

  return {
    job_id: jobId,
    url: `${apiBaseUrl}${fixturePath(kind)}`,
    status,
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-28T00:00:00Z",
    updated_at:
      status === "done"
        ? "2026-04-28T00:00:05Z"
        : "2026-04-28T00:00:00Z",
    sections: {},
    sidebar_payload: null,
    cached: false,
    next_poll_ms: 500,
    page_title: "Archive staleness fixture",
    page_kind: "article",
    utterance_count: 1,
  };
}

function nextFrameCompat(
  kind: FixtureKind,
  response: ServerResponse<IncomingMessage>,
): void {
  const count = (frameCompatCalls.get(kind) ?? 0) + 1;
  frameCompatCalls.set(kind, count);

  if (kind === "transient" && count <= 2) {
    writeJson(response, 503, { error_code: "temporarily_unavailable" });
    return;
  }

  const hasArchive =
    kind === "fallback" ||
    (kind === "mid-poll" && count >= 4) ||
    (kind === "transient" && count >= 3);
  const canIframe = kind === "fallback";

  writeJson(response, 200, {
    can_iframe: canIframe,
    blocking_header: canIframe
      ? null
      : "content-security-policy: frame-ancestors 'none'",
    csp_frame_ancestors: canIframe ? null : "frame-ancestors 'none'",
    has_archive: hasArchive,
  });
}

async function installClockAndOpenJob(page: Page, jobId: string): Promise<void> {
  await page.clock.install({ time: new Date("2026-04-28T00:00:00Z") });
  await page.goto(`${webBaseUrl}/analyze?job=${jobId}`);
  await expect(page.getByTestId("preview-mode-selector")).toBeVisible({
    timeout: 10_000,
  });
}

async function fastForward(page: Page, amount: string): Promise<void> {
  await page.clock.fastForward(amount);
}

async function installMainDocumentLoadSentinel(
  page: Page,
  storageKey: string,
): Promise<void> {
  await page.addInitScript((key) => {
    const win = window as Window & { __archiveStalenessLoads?: number };
    const next = Number(window.sessionStorage.getItem(key) ?? "0") + 1;
    window.sessionStorage.setItem(key, String(next));
    win.__archiveStalenessLoads = next;
  }, storageKey);
}

async function mainDocumentLoadCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    const win = window as Window & { __archiveStalenessLoads?: number };
    return win.__archiveStalenessLoads ?? 0;
  });
}

async function installSeenTestIdTracker(
  page: Page,
  testIds: string[],
): Promise<void> {
  await page.addInitScript((ids) => {
    const win = window as Window & { __archiveStalenessSeenTestIds?: string[] };
    const seen = new Set<string>();
    const record = () => {
      for (const testId of ids) {
        if (document.querySelector(`[data-testid="${testId}"]`)) {
          seen.add(testId);
        }
      }
      win.__archiveStalenessSeenTestIds = Array.from(seen);
    };
    const start = () => {
      record();
      new MutationObserver(record).observe(document.documentElement, {
        childList: true,
        subtree: true,
      });
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
      start();
    }
  }, testIds);
}

async function seenTestIds(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const win = window as Window & { __archiveStalenessSeenTestIds?: string[] };
    return win.__archiveStalenessSeenTestIds ?? [];
  });
}

async function installPreviewChainTracker(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const win = window as Window & { __archiveStalenessPreviewChain?: string[] };
    const chain: string[] = [];
    const recordState = (state: string) => {
      if (!chain.includes(state)) {
        chain.push(state);
        win.__archiveStalenessPreviewChain = [...chain];
      }
    };
    const record = () => {
      const original = document.querySelector(
        '[data-testid="page-frame-iframe"]',
      );
      if (
        original instanceof HTMLElement &&
        !original.hasAttribute("aria-hidden") &&
        getComputedStyle(original).opacity !== "0"
      ) {
        recordState("original-visible");
      }
      if (document.querySelector('[data-testid="page-frame-deciding"]')) {
        recordState("deciding");
      }
      if (
        document.querySelector('[data-testid="page-frame-archived-iframe"]')
      ) {
        recordState("archived");
      }
      if (document.querySelector('[data-testid="page-frame-screenshot"]')) {
        recordState("screenshot");
      }
      if (document.querySelector('[data-testid="page-frame-unavailable"]')) {
        recordState("unavailable");
      }
    };
    const start = () => {
      record();
      new MutationObserver(record).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["aria-hidden", "class", "style"],
        childList: true,
        subtree: true,
      });
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
      start();
    }
  });
}

async function previewChain(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const win = window as Window & { __archiveStalenessPreviewChain?: string[] };
    return win.__archiveStalenessPreviewChain ?? [];
  });
}

async function expectArchivedTabAvailable(page: Page): Promise<void> {
  const archived = page.getByTestId("preview-mode-archived");
  await expect(archived).toBeEnabled();
  await expect(archived).not.toHaveAttribute("title");
}

async function expectArchivedTabUnavailable(page: Page): Promise<void> {
  const archived = page.getByTestId("preview-mode-archived");
  await expect(archived).toBeDisabled();
  await expect(archived).toHaveAttribute(
    "title",
    "No archive available for this page",
  );
}

async function driveArchiveProbeTicks(
  page: Page,
  kind: FixtureKind,
  targetCalls: number,
): Promise<void> {
  await expect
    .poll(() => frameCompatCalls.get(kind) ?? 0, {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toBeGreaterThanOrEqual(1);

  while ((frameCompatCalls.get(kind) ?? 0) < targetCalls) {
    const before = frameCompatCalls.get(kind) ?? 0;
    await fastForward(page, "00:05");
    await expect
      .poll(() => frameCompatCalls.get(kind) ?? 0, {
        intervals: [100],
        timeout: PROBE_POLL_TIMEOUT_MS,
      })
      .toBeGreaterThan(before);
    if ((frameCompatCalls.get(kind) ?? 0) < targetCalls) {
      await expectArchivedTabAvailable(page);
    }
  }
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    const analyzeMatch = requestUrl.pathname.match(/^\/api\/analyze\/(.+)$/);
    if (request.method === "GET" && analyzeMatch) {
      const jobId = analyzeMatch[1];
      if (FIXTURES.has(jobId)) {
        writeJson(response, 200, jobState(jobId));
        return;
      }
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      const kind = fixtureKindFromUrl(targetUrl);
      if (kind) {
        nextFrameCompat(kind, response);
        return;
      }
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/archive-preview"
    ) {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      const kind = fixtureKindFromUrl(targetUrl);
      if (kind === "fallback") {
        response.writeHead(502, {
          "cache-control": "no-store, private",
          "content-type": "text/plain; charset=utf-8",
        });
        response.end("Archive unavailable");
        return;
      }
      if (kind === "mid-poll" || kind === "transient") {
        response.writeHead(200, {
          "cache-control": "no-store, private",
          "content-security-policy":
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'",
          "content-type": "text/html; charset=utf-8",
        });
        response.end("<!doctype html><h1>Archived preview fixture</h1>");
        return;
      }
      writeJson(response, 404, { detail: "Archive unavailable" });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
      const targetUrl = requestUrl.searchParams.get("url") ?? "";
      const kind = fixtureKindFromUrl(targetUrl);
      writeJson(response, 200, {
        screenshot_url: kind === "fallback" ? SCREENSHOT_URL : null,
      });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === fixturePath("fallback")) {
      response.writeHead(200, {
        "content-type": "text/html; charset=utf-8",
      });
      response.end("<!doctype html><h1>Visible original fixture</h1>");
      return;
    }
    if (request.method === "GET" && requestUrl.pathname.startsWith("/fixture/")) {
      response.writeHead(200, {
        "content-security-policy": "frame-ancestors 'none'",
        "content-type": "text/html; charset=utf-8",
      });
      response.end("<!doctype html><h1>Blocked original fixture</h1>");
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

test.beforeEach(() => {
  analyzeCalls = new Map<string, number>();
  frameCompatCalls = new Map<string, number>();
});

test("archive arriving mid-poll keeps Archived available and renders without reload", async ({
  page,
}) => {
  await installMainDocumentLoadSentinel(
    page,
    `archive-staleness-loads:${MID_POLL_JOB_ID}`,
  );
  await installClockAndOpenJob(page, MID_POLL_JOB_ID);
  await expect.poll(() => mainDocumentLoadCount(page), {
    intervals: [100],
    timeout: PROBE_POLL_TIMEOUT_MS,
  }).toBe(1);
  await expect(page.getByTestId("page-frame-iframe")).toBeVisible();
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(0);
  await expectArchivedTabAvailable(page);

  await driveArchiveProbeTicks(page, "mid-poll", 4);
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible({
    timeout: 10_000,
  });
  await expectArchivedTabAvailable(page);
  await expect(page.getByTestId("page-frame-screenshot")).toHaveCount(0);
  await expect(page.getByTestId("page-frame-unavailable")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/analyze\\?job=${MID_POLL_JOB_ID}$`));
  expect(await mainDocumentLoadCount(page)).toBe(1);
});

test("terminal job waits through 10s grace before disabling Archived", async ({
  page,
}) => {
  await installClockAndOpenJob(page, TERMINAL_GRACE_JOB_ID);
  await expectArchivedTabAvailable(page);

  await fastForward(page, "00:01");
  await expect(page.getByTestId("analysis-sidebar")).toHaveAttribute(
    "data-job-status",
    "done",
  );
  await expectArchivedTabAvailable(page);

  await fastForward(page, "00:09");
  await expectArchivedTabAvailable(page);

  await fastForward(page, "00:02");
  await expectArchivedTabUnavailable(page);
  await expect(page.getByTestId("page-frame-unavailable")).toBeVisible();
});

test("300s wall-clock cap disables Archived for a still-analyzing job", async ({
  page,
}) => {
  await installClockAndOpenJob(page, CAP_JOB_ID);
  await expectArchivedTabAvailable(page);

  await fastForward(page, "05:00");

  await expectArchivedTabUnavailable(page);
  await expect(page.getByTestId("page-frame-unavailable")).toBeVisible();
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveCount(0);
});

test("transient frame-compat failures retry without disabling Archived", async ({
  page,
}) => {
  await installClockAndOpenJob(page, TRANSIENT_JOB_ID);
  await expect(page.getByTestId("page-frame-iframe")).toBeVisible();
  await expect
    .poll(() => frameCompatCalls.get("transient") ?? 0, {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toBe(1);
  await expectArchivedTabAvailable(page);

  await fastForward(page, "00:05");
  await expect
    .poll(() => frameCompatCalls.get("transient") ?? 0, {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toBe(2);
  await expectArchivedTabAvailable(page);

  await fastForward(page, "00:05");

  await expect
    .poll(() => frameCompatCalls.get("transient") ?? 0, {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toBeGreaterThanOrEqual(3);
  await expectArchivedTabAvailable(page);
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByTestId("page-frame-unavailable")).toHaveCount(0);
});

test("blocked original automatically falls from Archived failure to Screenshot", async ({
  page,
}) => {
  await installSeenTestIdTracker(page, ["page-frame-archived-iframe"]);
  await installPreviewChainTracker(page);
  await installClockAndOpenJob(page, FALLBACK_JOB_ID);

  const originalFrame = page.getByTestId("page-frame-iframe");
  await expect(originalFrame).toBeVisible();
  await expect(originalFrame).not.toHaveAttribute("aria-hidden");
  await expect
    .poll(() => previewChain(page), {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toContain("original-visible");
  await expect(page.getByTestId("page-frame-deciding")).toHaveCount(0);
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveCount(0);
  await expect(page.getByTestId("page-frame-screenshot")).toHaveCount(0);

  await originalFrame.dispatchEvent("error");
  await expect(page.getByTestId("page-frame-deciding")).toBeVisible({
    timeout: 10_000,
  });
  await expect
    .poll(() => previewChain(page), {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toContain("deciding");
  await expect(originalFrame).toHaveCount(0);

  await fastForward(page, "00:15");
  await expect
    .poll(() => seenTestIds(page), {
      intervals: [100],
      timeout: PROBE_POLL_TIMEOUT_MS,
    })
    .toContain("page-frame-archived-iframe");
  await expect(page.getByTestId("page-frame-screenshot")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveCount(0);
  await expect(page.getByTestId("page-frame-unavailable")).toHaveCount(0);
  const chain = await previewChain(page);
  expect(chain).toEqual([
    "original-visible",
    "deciding",
    "archived",
    "screenshot",
  ]);
});
