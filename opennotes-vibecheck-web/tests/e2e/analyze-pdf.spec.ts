import { expect, test, type FrameLocator, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { stopWebProcess } from "./_helpers/web-process";

const PDF_JOB_ID = "55555555-5555-7555-8555-555555555555";
const IMAGE_JOB_ID = "55555555-5555-7555-8555-555555555556";
const ATTEMPT_ID = "66666666-6666-7666-8666-666666666666";
const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PDF_GCS_KEY = "pdfs/e2e-policy.pdf";
const IMAGE_PDF_GCS_KEY = `image-uploads/${IMAGE_JOB_ID}/generated.pdf`;
const MAX_PDF_BYTES = 50 * 1024 * 1024;

let apiServer: Server;
let apiBaseUrl = "";
let webBaseUrl = "";
let webProcess: ChildProcess | null = null;
let webLogs = "";
let uploadRequestCount = 0;
let signedUploadRequestCount = 0;
let analyzePdfRequestCount = 0;
let uploadImagesRequestCount = 0;
let signedImageUploadRequestCount = 0;
let analyzeImagesRequestCount = 0;
let frameCompatRequestCount = 0;
let screenshotRequestCount = 0;
let signedUploadContentType = "";
let signedUploadBody = Buffer.alloc(0);
let analyzePdfBody: unknown = null;
let uploadImagesBody: unknown = null;
let analyzeImagesBody: unknown = null;
let signedImageContentTypes: string[] = [];

async function runWebCommand(
  args: string[],
  env: NodeJS.ProcessEnv,
): Promise<void> {
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

function writeCorsNoContent(response: ServerResponse<IncomingMessage>): void {
  response.writeHead(204, {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "PUT, OPTIONS",
    "access-control-allow-headers": "content-type",
  });
  response.end();
}

function minimalPdf(): Buffer {
  return Buffer.from(
    "%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n",
  );
}

function sidebarPayload() {
  return {
    source_url: "pdfs/e2e-policy.pdf",
    page_title: "PDF E2E Fixture",
    page_kind: "article",
    scraped_at: "2026-05-04T18:00:00Z",
    cached: false,
    cached_at: null,
    headline: {
      text: "PDF E2E Fixture",
      kind: "stock",
      unavailable_inputs: [],
    },
    utterances: [{ position: 1, utterance_id: "pdf-flash-utt" }],
    safety: {
      recommendation: null,
      harmful_content_matches: [],
    },
    web_risk: { findings: [] },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      flashpoint_matches: [
        {
          scan_type: "conversation_flashpoint",
          utterance_id: "pdf-flash-utt",
          derailment_score: 71,
          risk_level: "Heated",
          reasoning: "The PDF discussion gets sharper around the cited turn.",
          context_messages: 2,
        },
      ],
      scd: {
        summary: "A short PDF thread turns tense.",
        narrative: "The exchange escalates around one source quote.",
        tone_labels: ["tense"],
        per_speaker_notes: {},
        speaker_arcs: [],
        insufficient_conversation: false,
      },
    },
    facts_claims: {
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
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
        subjective_claims: [],
      },
    },
  };
}

function pdfJobState() {
  return {
    job_id: PDF_JOB_ID,
    url: PDF_GCS_KEY,
    status: "done",
    source_type: "pdf",
    pdf_archive_url: `/api/archive-preview?source_type=pdf&job_id=${PDF_JOB_ID}`,
    attempt_id: ATTEMPT_ID,
    created_at: "2026-05-04T18:00:00Z",
    updated_at: "2026-05-04T18:00:01Z",
    sections: {},
    sidebar_payload: sidebarPayload(),
    sidebar_payload_complete: true,
    cached: false,
    next_poll_ms: 1500,
    page_title: "PDF E2E Fixture",
    page_kind: "article",
    utterance_count: 1,
  };
}

function imageJobState() {
  return {
    ...pdfJobState(),
    job_id: IMAGE_JOB_ID,
    url: IMAGE_PDF_GCS_KEY,
    pdf_archive_url: `/api/archive-preview?source_type=pdf&job_id=${IMAGE_JOB_ID}`,
    sidebar_payload: {
      ...sidebarPayload(),
      source_url: IMAGE_PDF_GCS_KEY,
      page_title: "Image Upload E2E Fixture",
      headline: {
        text: "Image Upload E2E Fixture",
        kind: "stock",
        unavailable_inputs: [],
      },
    },
    page_title: "Image Upload E2E Fixture",
  };
}

function archiveHtml(): string {
  return `<!doctype html>
    <html>
      <head>
        <style>
          body { margin: 0; font-family: Arial, sans-serif; line-height: 1.5; }
          article { padding: 32px; }
          .spacer { height: 900px; }
          p { padding: 16px; border: 1px solid #d4d4d8; }
        </style>
      </head>
      <body>
        <article>
          <p>Introductory PDF text before the cited utterance.</p>
          <div class="spacer"></div>
          <p data-utterance-id="pdf-flash-utt">Archived PDF utterance anchor.</p>
        </article>
      </body>
    </html>`;
}

function resetCounters(): void {
  uploadRequestCount = 0;
  signedUploadRequestCount = 0;
  analyzePdfRequestCount = 0;
  uploadImagesRequestCount = 0;
  signedImageUploadRequestCount = 0;
  analyzeImagesRequestCount = 0;
  frameCompatRequestCount = 0;
  screenshotRequestCount = 0;
  signedUploadContentType = "";
  signedUploadBody = Buffer.alloc(0);
  analyzePdfBody = null;
  uploadImagesBody = null;
  analyzeImagesBody = null;
  signedImageContentTypes = [];
}

function archiveFrame(page: Page): FrameLocator {
  return page.frameLocator('[data-testid="page-frame-archived-iframe"]');
}

async function expectArchivedTargetInViewport(page: Page): Promise<void> {
  await expect
    .poll(async () =>
      archiveFrame(page)
        .locator('[data-utterance-id="pdf-flash-utt"]')
        .evaluate((element) => {
          const rect = element.getBoundingClientRect();
          return rect.top >= 0 && rect.bottom <= window.innerHeight;
        }),
    )
    .toBe(true);
}

async function uploadValidPdf(page: Page): Promise<void> {
  await page.goto(webBaseUrl);
  await page.getByTestId("vibecheck-pdf-input").setInputFiles({
    name: "policy.pdf",
    mimeType: "application/pdf",
    buffer: minimalPdf(),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page).toHaveURL(new RegExp(`/analyze\\?job=${PDF_JOB_ID}`));
}

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? "/", apiBaseUrl || "http://x");
    if (
      request.method === "OPTIONS" &&
      (requestUrl.pathname.startsWith(`/signed-image/${IMAGE_JOB_ID}/`) ||
        requestUrl.pathname === `/signed-upload/${PDF_JOB_ID}`)
    ) {
      writeCorsNoContent(response);
      return;
    }
    if (request.method === "POST" && requestUrl.pathname === "/api/upload-images") {
      uploadImagesRequestCount += 1;
      const chunks: Buffer[] = [];
      request.on("data", (chunk) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      request.on("end", () => {
        uploadImagesBody = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        writeJson(response, 200, {
          job_id: IMAGE_JOB_ID,
          images: [
            {
              ordinal: 0,
              gcs_key: `image-uploads/${IMAGE_JOB_ID}/source/000-first`,
              upload_url: `${apiBaseUrl}/signed-image/${IMAGE_JOB_ID}/0`,
            },
            {
              ordinal: 1,
              gcs_key: `image-uploads/${IMAGE_JOB_ID}/source/001-second`,
              upload_url: `${apiBaseUrl}/signed-image/${IMAGE_JOB_ID}/1`,
            },
          ],
        });
      });
      return;
    }
    if (
      request.method === "PUT" &&
      requestUrl.pathname.startsWith(`/signed-image/${IMAGE_JOB_ID}/`)
    ) {
      signedImageUploadRequestCount += 1;
      signedImageContentTypes.push(String(request.headers["content-type"] ?? ""));
      request.on("end", () => {
        writeCorsNoContent(response);
      });
      request.resume();
      return;
    }
    if (request.method === "POST" && requestUrl.pathname === "/api/analyze-images") {
      analyzeImagesRequestCount += 1;
      const chunks: Buffer[] = [];
      request.on("data", (chunk) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      request.on("end", () => {
        analyzeImagesBody = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        writeJson(response, 200, {
          job_id: IMAGE_JOB_ID,
          status: "pending",
          cached: false,
        });
      });
      return;
    }
    if (request.method === "POST" && requestUrl.pathname === "/api/upload-pdf") {
      uploadRequestCount += 1;
      writeJson(response, 200, {
        gcs_key: PDF_GCS_KEY,
        upload_url: `${apiBaseUrl}/signed-upload/${PDF_JOB_ID}`,
      });
      return;
    }
    if (
      request.method === "PUT" &&
      requestUrl.pathname === `/signed-upload/${PDF_JOB_ID}`
    ) {
      signedUploadRequestCount += 1;
      signedUploadContentType = request.headers["content-type"] ?? "";
      const chunks: Buffer[] = [];
      request.on("data", (chunk) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      request.on("end", () => {
        signedUploadBody = Buffer.concat(chunks);
        writeCorsNoContent(response);
      });
      return;
    }
    if (request.method === "POST" && requestUrl.pathname === "/api/analyze-pdf") {
      analyzePdfRequestCount += 1;
      const chunks: Buffer[] = [];
      request.on("data", (chunk) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      request.on("end", () => {
        try {
          analyzePdfBody = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        } catch {
          analyzePdfBody = null;
        }
        writeJson(response, 200, {
          job_id: PDF_JOB_ID,
          status: "pending",
          cached: false,
        });
      });
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${PDF_JOB_ID}`
    ) {
      writeJson(response, 200, pdfJobState());
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === `/api/analyze/${IMAGE_JOB_ID}`
    ) {
      writeJson(response, 200, imageJobState());
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/pdf-read") {
      const jobId = requestUrl.searchParams.get("job_id");
      if (jobId !== PDF_JOB_ID && jobId !== IMAGE_JOB_ID) {
        writeJson(response, 404, { error_code: "not_found" });
        return;
      }
      response.writeHead(307, {
        location: `${apiBaseUrl}/pdf-source/${jobId}.pdf`,
        "cache-control": "no-store, private",
      });
      response.end();
      return;
    }
    if (
      request.method === "GET" &&
      (requestUrl.pathname === `/pdf-source/${PDF_JOB_ID}.pdf` ||
        requestUrl.pathname === `/pdf-source/${IMAGE_JOB_ID}.pdf`)
    ) {
      const body = minimalPdf();
      response.writeHead(200, {
        "content-type": "application/pdf",
        "content-length": String(body.byteLength),
      });
      response.end(body);
      return;
    }
    if (
      request.method === "GET" &&
      requestUrl.pathname === "/api/archive-preview"
    ) {
      if (
        requestUrl.searchParams.get("source_type") === "pdf" &&
        [PDF_JOB_ID, IMAGE_JOB_ID].includes(requestUrl.searchParams.get("job_id") ?? "")
      ) {
        response.writeHead(200, {
          "cache-control": "no-store, private",
          "content-type": "text/html; charset=utf-8",
        });
        response.end(archiveHtml());
        return;
      }
      writeJson(response, 404, { detail: "Archive unavailable" });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/frame-compat") {
      frameCompatRequestCount += 1;
      writeJson(response, 200, {
        can_iframe: true,
        blocking_header: null,
        csp_frame_ancestors: null,
        has_archive: false,
      });
      return;
    }
    if (request.method === "GET" && requestUrl.pathname === "/api/screenshot") {
      screenshotRequestCount += 1;
      writeJson(response, 200, { screenshot_url: null });
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

test.beforeEach(() => {
  resetCounters();
});

test.afterAll(async () => {
  if (webProcess) {
    await stopWebProcess(webProcess);
  }
  if (apiServer) {
    await new Promise<void>((resolve) => apiServer.close(() => resolve()));
  }
});

test("PDF upload happy path shows Original PDF and Archived annotated HTML", async ({
  page,
}) => {
  await uploadValidPdf(page);

  await expect(page.getByTestId("analysis-sidebar")).toBeVisible();
  await expect(page.getByTestId("headline-summary-text")).toContainText(
    "PDF E2E Fixture",
  );
  await expect(page.getByTestId("flashpoint-score")).toHaveText(
    "derailment ~71/100",
  );
  await expect(page.getByTestId("flashpoint-reasoning")).toContainText(
    "gets sharper around the cited turn",
  );
  await page.getByRole("button", { name: "Original" }).click();
  await expect(page.getByTestId("page-frame-pdf-embed")).toHaveAttribute(
    "src",
    `/api/pdf-read?job_id=${PDF_JOB_ID}`,
  );
  await expect(page.getByTestId("page-frame-iframe")).toHaveCount(0);
  await expect(page.getByTestId("preview-mode-screenshot")).toBeDisabled();
  await expect(page.getByTestId("preview-mode-screenshot")).toHaveAttribute(
    "aria-label",
    "Not available for PDFs",
  );

  const archivedButton = page.getByRole("button", { name: "Snapshot" });
  await expect(archivedButton).toBeEnabled();
  await archivedButton.click();
  await expect(page.getByTestId("page-frame-archived-iframe")).toBeVisible();
  await expect(page.getByTestId("page-frame-archived-iframe")).toHaveAttribute(
    "src",
    `/api/archive-preview?source_type=pdf&job_id=${PDF_JOB_ID}`,
  );
  await expect(
    archiveFrame(page).locator('[data-utterance-id="pdf-flash-utt"]'),
  ).toBeVisible();

  expect(uploadRequestCount).toBe(1);
  expect(signedUploadRequestCount).toBe(1);
  expect(analyzePdfRequestCount).toBe(1);
  expect(signedUploadContentType).toBe("application/pdf");
  expect(signedUploadBody.equals(minimalPdf())).toBe(true);
  expect(analyzePdfBody).toEqual({
    gcs_key: PDF_GCS_KEY,
    filename: "policy.pdf",
  });
  expect(frameCompatRequestCount).toBe(0);
  expect(screenshotRequestCount).toBe(0);
});

test("image batch upload reaches the normal analyze page with generated PDF original", async ({
  page,
}) => {
  await page.goto(webBaseUrl);
  await page.getByTestId("vibecheck-pdf-input").setInputFiles([
    {
      name: "first.png",
      mimeType: "image/png",
      buffer: Buffer.from("png bytes"),
    },
    {
      name: "second.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from("jpeg bytes"),
    },
  ]);
  await expect(page.getByTestId("upload-selection-copy")).toContainText(
    "2 images selected",
  );

  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page).toHaveURL(new RegExp(`/analyze\\?job=${IMAGE_JOB_ID}`));

  await expect(page.getByTestId("headline-summary-text")).toContainText(
    "Image Upload E2E Fixture",
  );
  await page.getByRole("button", { name: "Original" }).click();
  await expect(page.getByTestId("page-frame-pdf-embed")).toHaveAttribute(
    "src",
    `/api/pdf-read?job_id=${IMAGE_JOB_ID}`,
  );
  expect(uploadImagesRequestCount).toBe(1);
  expect(signedImageUploadRequestCount).toBe(2);
  expect(analyzeImagesRequestCount).toBe(1);
  expect(signedImageContentTypes).toEqual(["image/png", "image/jpeg"]);
  expect(uploadImagesBody).toEqual({
    images: [
      { filename: "first.png", content_type: "image/png", size_bytes: 9 },
      { filename: "second.jpg", content_type: "image/jpeg", size_bytes: 10 },
    ],
  });
  expect(analyzeImagesBody).toEqual({ job_id: IMAGE_JOB_ID });
});

test("PDF utterance ref switches to Archived and targets the cited anchor", async ({
  page,
}) => {
  await uploadValidPdf(page);

  await page.getByText("Tone/dynamics").click();
  await expect(page.getByTestId("flashpoint-utterance-ref")).toBeVisible();
  await page.getByTestId("flashpoint-utterance-ref").click();
  await expect(page.getByRole("button", { name: "Snapshot" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const target = archiveFrame(page).locator(
    '[data-utterance-id="pdf-flash-utt"]',
  );
  await expect(target).toBeVisible();
  await expect(target).toHaveAttribute("data-vibecheck-ring", "");
  await expectArchivedTargetInViewport(page);
});

test("PDF client validation rejects oversize and non-PDF files before submit", async ({
  page,
}) => {
  await page.goto(webBaseUrl);

  const tmpDir = await mkdtemp(join(tmpdir(), "vibecheck-pdf-e2e-"));
  try {
    const oversizedPath = join(tmpDir, "too-big.pdf");
    await writeFile(oversizedPath, Buffer.alloc(MAX_PDF_BYTES + 1));
    await page.getByTestId("vibecheck-pdf-input").setInputFiles(oversizedPath);
    await page.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "PDF must be 50 MB or less.",
    );
  } finally {
    await rm(tmpDir, { recursive: true, force: true });
  }

  await page.getByTestId("vibecheck-pdf-input").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a pdf"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByRole("alert")).toHaveText("That image type is not supported.");
  expect(uploadRequestCount).toBe(0);
  expect(signedUploadRequestCount).toBe(0);
  expect(analyzePdfRequestCount).toBe(0);
});
