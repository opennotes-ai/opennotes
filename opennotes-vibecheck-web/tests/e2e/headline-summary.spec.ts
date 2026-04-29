import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { createServer, type Server } from "node:http";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";
import {
  ALL_SECTION_SLUGS,
  QUIZLET_REFERENCE_URL,
  submitUrlAndWaitForAnalyze,
  waitForAllSectionsTerminal,
} from "./fixtures/quizlet";

const SERVER_HEADLINE_JOB_ID = "11111111-1111-7111-8111-111111111111";
const FALLBACK_HEADLINE_JOB_ID = "33333333-3333-7333-8333-333333333333";
const ATTEMPT_ID = "22222222-2222-7222-8222-222222222222";
const SOURCE_URL = "https://WWW.www.Example.COM/news/story-title.html";
const PROD_HEADLINE_JOB_ID = "abd714b0-bd5d-405e-83ef-419be5261866";
const PROD_HEADLINE_BASE_URL =
  process.env.VIBECHECK_E2E_PROD_HEADLINE_BASE_URL ??
  "https://vibecheck.opennotes.ai";
const SERVER_HEADLINE_TEXT =
  "The server-generated headline now includes the full policy synthesis, uncertainty rationale, operational constraints, and downstream governance context in one uninterrupted narrative sentence to prove long-trim-sensitive behavior across both browser and slot rendering paths.";
const FALLBACK_HEADLINE_TITLE =
  "The fallback headline should keep a long source-derived title in full so no cap or ellipsis hides the context, including punctuation, date references, and the nuanced framing that helps distinguish related but dissimilar stories from the same feed";
const FALLBACK_HEADLINE_TEXT = `example.com — ${FALLBACK_HEADLINE_TITLE} — appears clean`;
const HEADLINE_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 1080 },
  { name: "mobile", width: 390, height: 844 },
] as const;

type HeadlineViewport = (typeof HEADLINE_VIEWPORTS)[number];
type HeadlineSource = "server" | "fallback" | "auto";
type HeadlineViewportOptions = {
  baseUrl?: string;
  jobId?: string;
  screenshotPrefix?: string;
};

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));

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

function sectionData(slug: string): Record<string, unknown> {
  if (slug === "safety__moderation") return { harmful_content_matches: [] };
  if (slug === "safety__web_risk") return { findings: [] };
  if (slug === "safety__image_moderation") return { matches: [] };
  if (slug === "safety__video_moderation") return { matches: [] };
  if (slug === "tone_dynamics__flashpoint") {
    return { flashpoint_matches: [] };
  }
  if (slug === "tone_dynamics__scd") {
    return {
      scd: {
        narrative: "The discussion stays informational and stable.",
        summary: "Stable informational tone.",
        tone_labels: ["informational"],
        per_speaker_notes: {},
        speaker_arcs: [],
        insufficient_conversation: true,
      },
    };
  }
  if (slug === "facts_claims__dedup") {
    return {
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
      },
    };
  }
  if (slug === "facts_claims__known_misinfo") {
    return { known_misinformation: [] };
  }
  if (slug === "opinions_sentiments__sentiment") {
    return {
      sentiment_stats: {
        per_utterance: [],
        positive_pct: 0,
        negative_pct: 0,
        neutral_pct: 100,
        mean_valence: 0,
      },
    };
  }
  return { subjective_claims: [] };
}

function sidebarPayload(headline: Record<string, unknown> | null) {
  return {
    cached_at: "2026-04-23T22:09:00Z",
    headline,
    safety: {
      harmful_content_matches: [],
      recommendation: {
        level: "safe",
        rationale: "No safety concerns are present in the mocked payload.",
        top_signals: [],
        unavailable_inputs: [],
      },
    },
    web_risk: { findings: [] },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      flashpoint_matches: [],
      scd: sectionData("tone_dynamics__scd").scd,
    },
    facts_claims: {
      claims_report: sectionData("facts_claims__dedup").claims_report,
      known_misinformation: [],
    },
    opinions_sentiments: {
      opinions_report: {
        sentiment_stats:
          sectionData("opinions_sentiments__sentiment").sentiment_stats,
        subjective_claims: [],
      },
    },
  };
}

function terminalJobState(jobId: string) {
  const sections = Object.fromEntries(
    ALL_SECTION_SLUGS.map((slug) => [
      slug,
      {
        state: "done",
        attempt_id: ATTEMPT_ID,
        data: sectionData(slug),
        finished_at: "2026-04-23T22:09:00Z",
      },
    ]),
  );
  const headline =
    jobId === SERVER_HEADLINE_JOB_ID
      ? { text: SERVER_HEADLINE_TEXT, kind: "synthesized" }
      : null;
  return {
    job_id: jobId,
    url: SOURCE_URL,
    status: "done",
    attempt_id: ATTEMPT_ID,
    created_at: "2026-04-23T22:08:00Z",
    updated_at: "2026-04-23T22:09:00Z",
    sections,
    sidebar_payload: sidebarPayload(headline),
    cached: true,
    next_poll_ms: 1500,
    page_title: jobId === FALLBACK_HEADLINE_JOB_ID
      ? FALLBACK_HEADLINE_TITLE
      : "Groups are now classes",
    page_kind: "article",
    utterance_count: 3,
  };
}

async function assertHeadlineNoClippingStyles(page: Page): Promise<void> {
  const style = await page.getByTestId("headline-summary-text").evaluate((node) => {
    const textElement = node as HTMLElement;
    const container = textElement.closest("section") as HTMLElement | null;
    if (!container) {
      throw new Error("headline-summary section not found");
    }
    const textStyles = getComputedStyle(textElement);
    const containerStyles = getComputedStyle(container);
    return {
      textOverflow: textStyles.textOverflow,
      whiteSpace: textStyles.whiteSpace,
      lineClamp: textStyles.getPropertyValue("-webkit-line-clamp"),
      textElementOverflow: textStyles.overflow,
      textElementOverflowX: textStyles.overflowX,
      textElementOverflowY: textStyles.overflowY,
      overflow: containerStyles.overflow,
      overflowX: containerStyles.overflowX,
      overflowY: containerStyles.overflowY,
      lineHeight: textStyles.lineHeight,
      scrollHeight: textElement.scrollHeight,
      clientHeight: textElement.clientHeight,
    };
  });

  expect(style.textOverflow, "headline text should not apply ellipsis truncation").not
    .toMatch(/ellipsis/i);
  expect(
    style.lineClamp,
    "headline text should not line-clamp the summary",
  ).not.toMatch(/^\d+$/);
  expect(
    style.whiteSpace,
    "headline text should allow wrapping",
  ).not.toBe("nowrap");
  expect(
    style.overflow,
    "headline text container should not clip overflow",
  ).not.toBe("hidden");
  expect(
    style.overflowX,
    "headline text container should not hide horizontal overflow",
  ).not.toBe("hidden");
  expect(
    style.overflowY,
    "headline text container should not hide vertical overflow",
  ).not.toBe("hidden");
  expect(
    style.textElementOverflow,
    "headline text element should not clip horizontal overflow",
  ).not.toBe("hidden");
  expect(
    style.textElementOverflowX,
    "headline text element should not hide horizontal overflow",
  ).not.toBe("hidden");
  expect(
    style.textElementOverflowY,
    "headline text element should not hide vertical overflow",
  ).not.toBe("hidden");
  const lineHeight = parseFloat(style.lineHeight);
  const lines = Number.isFinite(lineHeight) && lineHeight > 0
    ? style.scrollHeight / lineHeight
    : 0;
  expect(
    lines,
    "headline text should expand across lines instead of being force-clipped",
  ).toBeGreaterThan(1);
  const heightTolerancePx = 1;
  expect(
    style.scrollHeight,
    "headline text should not be visually clipped by text element height constraints",
  ).toBeLessThanOrEqual(style.clientHeight + heightTolerancePx);
}

async function assertHeadlineSummaryAtViewport(
  page: Page,
  source: HeadlineSource,
  expectedText: string | null,
  viewport: HeadlineViewport,
  testInfo: TestInfo,
  options: HeadlineViewportOptions = {},
): Promise<string> {
  const analyzeJobId = options.jobId
    ? options.jobId
    : source === "server"
      ? SERVER_HEADLINE_JOB_ID
      : FALLBACK_HEADLINE_JOB_ID;
  if (source === "auto" && !options.jobId) {
    throw new Error(
      "assertHeadlineSummaryAtViewport('auto') requires options.jobId to be set",
    );
  }

  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto(`${options.baseUrl ?? webBaseUrl}/analyze?job=${analyzeJobId}`);

  const headlineText = await assertHeadlineSummary(page, source);
  if (expectedText !== null) {
    expect(headlineText).toBe(expectedText);

    const normalizedText = headlineText.normalize("NFC");
    expect(normalizedText.length).toBeGreaterThanOrEqual(expectedText.length);
    expect(normalizedText).toBe(expectedText);
  } else {
    expect(
      headlineText.length,
      "headline summary must render text for the production regression job",
    ).toBeGreaterThan(0);
  }

  await assertHeadlineNoClippingStyles(page);
  const screenshotPath = testInfo.outputPath(
    `headline-summary-${options.screenshotPrefix ?? source}-${viewport.name}.png`,
  );
  await page.screenshot({
    path: screenshotPath,
    fullPage: true,
  });
  expect(screenshotPath).toBeTruthy();

  return headlineText;
}

async function assertHeadlinePrecedesSafety(page: Page): Promise<void> {
  const headlinePrecedesSafety = await page.evaluate(() => {
    const h = document.querySelector('[data-testid="headline-summary"]');
    const s = document.querySelector(
      '[data-testid="safety-recommendation-report"]',
    );
    if (!h || !s) {
      throw new Error(
        `Cannot compare headline/safety order: headline-summary=${Boolean(
          h,
        )}, safety-recommendation-report=${Boolean(s)}`,
      );
    }
    return Boolean(
      h.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(
    headlinePrecedesSafety,
    "headline-summary must appear above safety-recommendation-report in the sidebar",
  ).toBe(true);
}

async function assertHeadlineSummary(
  page: Page,
  source: HeadlineSource | undefined,
): Promise<string> {
  await expect(page.locator('[data-testid="analyze-layout"]')).toBeVisible({
    timeout: 30_000,
  });
  const finalStates = await waitForAllSectionsTerminal(page, {
    timeoutMs: 30_000,
  });
  const doneCount = ALL_SECTION_SLUGS.filter(
    (slug) => finalStates[slug] === "done",
  ).length;
  expect(
    doneCount,
    `All sections must reach 'done' before the headline assertion (got ${doneCount}: ${JSON.stringify(finalStates)})`,
  ).toBe(ALL_SECTION_SLUGS.length);

  const headline = page.getByTestId("headline-summary");
  await expect(headline, "headline summation block must render").toBeVisible({
    timeout: 30_000,
  });

  const text = page.getByTestId("headline-summary-text");
  const headlineText = (await text.textContent())?.trim() ?? "";
  expect(
    headlineText.length,
    `headline-summary-text must be non-empty (got: ${JSON.stringify(headlineText)})`,
  ).toBeGreaterThan(0);

  const kind = await headline.getAttribute("data-headline-kind");
  expect(
    kind,
    `data-headline-kind must be 'stock' or 'synthesized' (got: ${JSON.stringify(kind)})`,
  ).toMatch(/^(stock|synthesized)$/);

  const headlineSource = await headline.getAttribute("data-headline-source");
  if (source === "server" || source === "fallback") {
    expect(
      headlineSource,
      `headline source should be '${source}' for this scenario`,
    ).toBe(source);
  } else {
    expect(
      headlineSource,
      "headline source should be explicit for analyzed jobs",
    ).toMatch(/^(server|fallback)$/);
  }
  await expect(
    text,
    "headline text must not render the read-more truncation chrome",
  ).not.toHaveAttribute("data-truncated", /.*/);

  const safetyRec = page.getByTestId("safety-recommendation-report");
  await expect(
    safetyRec,
    "safety-recommendation-report must render alongside the headline so we can verify ordering",
  ).toBeVisible({ timeout: 10_000 });
  await assertHeadlinePrecedesSafety(page);
  return headlineText;
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    const jobId = requestUrl.pathname.split("/").pop() ?? "";
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${jobId}` &&
      (jobId === SERVER_HEADLINE_JOB_ID || jobId === FALLBACK_HEADLINE_JOB_ID)
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(terminalJobState(jobId)));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/frame-compat"
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ can_iframe: true, blocking_header: null }));
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/screenshot"
    ) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ screenshot_url: null }));
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

test(
  "mocked terminal poll payload renders server headline source",
  async ({ page }, testInfo) => {
    const headlineText = await assertHeadlineSummaryAtViewport(
      page,
      "server",
      SERVER_HEADLINE_TEXT,
      HEADLINE_VIEWPORTS[0],
      testInfo,
    );
    expect(headlineText).toBe(SERVER_HEADLINE_TEXT);
  },
);

test(
  "mocked terminal poll payload without headline renders fallback source",
  async ({ page }, testInfo) => {
    const headlineText = await assertHeadlineSummaryAtViewport(
      page,
      "fallback",
      FALLBACK_HEADLINE_TEXT,
      HEADLINE_VIEWPORTS[0],
      testInfo,
    );
    expect(headlineText).toBe(FALLBACK_HEADLINE_TEXT);
  },
);

test(
  "mocked terminal poll payload renders long server headline on mobile viewport",
  async ({ page }, testInfo) => {
    const headlineText = await assertHeadlineSummaryAtViewport(
      page,
      "server",
      SERVER_HEADLINE_TEXT,
      HEADLINE_VIEWPORTS[1],
      testInfo,
    );
    expect(headlineText).toBe(SERVER_HEADLINE_TEXT);
  },
);

test(
  "mocked terminal poll payload without headline renders fallback source on mobile",
  async ({ page }, testInfo) => {
    const headlineText = await assertHeadlineSummaryAtViewport(
      page,
      "fallback",
      FALLBACK_HEADLINE_TEXT,
      HEADLINE_VIEWPORTS[1],
      testInfo,
    );
    expect(headlineText).toBe(FALLBACK_HEADLINE_TEXT);
  },
);

test("live upstream headline summary renders above safety-recommendation", async ({
  page,
}) => {
  test.skip(
    process.env.VIBECHECK_E2E_LIVE_UPSTREAM !== "1",
    "Set VIBECHECK_E2E_LIVE_UPSTREAM=1 to run the live upstream headline check.",
  );
  test.setTimeout(220_000);

  const { jobId, pendingError } = await submitUrlAndWaitForAnalyze(
    page,
    QUIZLET_REFERENCE_URL,
  );
  expect(
    pendingError,
    "Submitting the canonical Quizlet URL must not produce a pending_error redirect",
  ).toBeNull();
  expect(jobId, "AnalyzePage must be reached with ?job=<id>").toBeTruthy();

  await assertHeadlineSummary(page, "server");
});

test("post-deploy production headline regression for cited job at desktop and mobile", async ({
  page,
}, testInfo) => {
  test.skip(
    process.env.VIBECHECK_E2E_PROD_HEADLINE_REGRESSION !== "1" ||
      process.env.VIBECHECK_E2E_PROD_HEADLINE_CACHE_CLEARED !== "1",
    `Set VIBECHECK_E2E_PROD_HEADLINE_REGRESSION=1 and VIBECHECK_E2E_PROD_HEADLINE_CACHE_CLEARED=1 to run this post-deploy production regression for job ${PROD_HEADLINE_JOB_ID}. Before running, clear stale vibecheck_analyses / persisted headline data for the normalized source URL for that job.`,
  );
  test.setTimeout(180_000);

  for (const viewport of HEADLINE_VIEWPORTS) {
    await assertHeadlineSummaryAtViewport(page, "auto", null, viewport, testInfo, {
      baseUrl: PROD_HEADLINE_BASE_URL,
      jobId: PROD_HEADLINE_JOB_ID,
      screenshotPrefix: "prod",
    });
  }
});
