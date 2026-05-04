import createClient from "openapi-fetch";
import { GoogleAuth } from "google-auth-library";
import type { IdTokenClient } from "google-auth-library";
import type { paths, components } from "./generated-types";

export type SidebarPayload = components["schemas"]["SidebarPayload"];
export type AnalyzeResponse = components["schemas"]["AnalyzeResponse"];
export type JobState = components["schemas"]["JobState"];
export type SectionSlug = components["schemas"]["SectionSlug"];
export type SectionSlot = components["schemas"]["SectionSlot"];
export type SectionState = components["schemas"]["SectionState"];
export type JobStatus = components["schemas"]["JobStatus"];
export type ErrorCode = components["schemas"]["ErrorCode"];
export type RetryResponse = components["schemas"]["RetryResponse"];
export type PublicErrorCode = ErrorCode | "pdf_too_large" | "pdf_extraction_failed";

export interface UploadPdfResponse {
  gcs_key: string;
  upload_url: string;
}

export interface ApiErrorBody {
  error_code?: PublicErrorCode;
  message?: string;
  error_host?: string;
}

export const PUBLIC_ERROR_CODES: readonly PublicErrorCode[] = [
  "invalid_url",
  "unsafe_url",
  "unsupported_site",
  "upstream_error",
  "extraction_failed",
  "section_failure",
  "timeout",
  "rate_limited",
  "internal",
  "pdf_too_large",
  "pdf_extraction_failed",
  "upload_key_invalid",
  "upload_not_found",
  "invalid_pdf_type",
];

export function clampErrorCode(raw: unknown): PublicErrorCode | undefined {
  if (typeof raw !== "string") return undefined;
  return (PUBLIC_ERROR_CODES as readonly string[]).includes(raw)
    ? (raw as PublicErrorCode)
    : undefined;
}

const ANALYZE_SUBMIT_TIMEOUT_MS = 300_000;
const GCS_PUT_TIMEOUT_MS = 10 * 60_000;
const POLL_FETCH_TIMEOUT_MS = 60_000;
const DEFAULT_FETCH_TIMEOUT_MS = 60_000;
const FETCH_MAX_ATTEMPTS = 2;
const FETCH_RETRY_BASE_DELAY_MS = 250;
const IDENTITY_TOKEN_MAX_RETRIES = 3;
const TOKEN_FETCH_TIMEOUT_MS = 5_000;
const DEFAULT_DEV_BASE_URL = "http://localhost:8000";

function timeoutForRequest(request: Request): number {
  let pathname: string;
  try {
    pathname = new URL(request.url).pathname;
  } catch {
    return DEFAULT_FETCH_TIMEOUT_MS;
  }
  if (
    request.method === "POST" &&
    (pathname === "/api/analyze" || pathname === "/api/analyze-pdf")
  ) {
    return ANALYZE_SUBMIT_TIMEOUT_MS;
  }
  if (request.method === "PUT") {
    return GCS_PUT_TIMEOUT_MS;
  }
  return POLL_FETCH_TIMEOUT_MS;
}

export class VibecheckApiError extends Error {
  public errorBody: ApiErrorBody | null;
  public headers: Headers;

  constructor(
    message: string,
    public statusCode: number,
    errorBody: ApiErrorBody | null = null,
    headers?: Headers | Record<string, string> | null,
  ) {
    super(message);
    this.name = "VibecheckApiError";
    this.errorBody = errorBody;
    this.headers = headers
      ? headers instanceof Headers
        ? headers
        : new Headers(headers)
      : new Headers();
  }
}

let authInstance: GoogleAuth | null = null;
const idTokenClientCache = new Map<string, IdTokenClient>();

function getAuthInstance(): GoogleAuth {
  if (!authInstance) {
    authInstance = new GoogleAuth();
  }
  return authInstance;
}

export function normalizeHeaders(
  raw: Headers | Record<string, string | string[] | undefined> | null | undefined,
): Headers {
  if (!raw) return new Headers();
  if (raw instanceof Headers) return raw;
  const out = new Headers();
  for (const [key, value] of Object.entries(raw)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const v of value) out.append(key, v);
    } else {
      out.set(key, value);
    }
  }
  return out;
}

export async function getAuthorizationHeader(
  targetAudience: string,
): Promise<string | null> {
  if (process.env.NODE_ENV !== "production") return null;

  return new Promise<string | null>((resolve, reject) => {
    let settled = false;
    const timeoutId = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error("Identity token fetch timed out after 5s"));
      }
    }, TOKEN_FETCH_TIMEOUT_MS);

    (async () => {
      for (let attempt = 0; attempt < IDENTITY_TOKEN_MAX_RETRIES; attempt++) {
        try {
          const auth = getAuthInstance();
          let client = idTokenClientCache.get(targetAudience);
          if (!client) {
            client = await auth.getIdTokenClient(targetAudience);
            idTokenClientCache.set(targetAudience, client);
          }
          const rawHeaders = await client.getRequestHeaders();
          const headers = normalizeHeaders(rawHeaders);
          return headers.get("Authorization") || null;
        } catch (error) {
          if (attempt === IDENTITY_TOKEN_MAX_RETRIES - 1) throw error;
          await new Promise((r) =>
            setTimeout(r, 100 * 2 ** attempt),
          );
        }
      }
      return null;
    })().then(
      (value) => {
        if (!settled) {
          settled = true;
          clearTimeout(timeoutId);
          resolve(value);
        }
      },
      (error) => {
        if (!settled) {
          settled = true;
          clearTimeout(timeoutId);
          reject(error);
        }
      },
    );
  });
}

export function resolveBaseUrl(): string {
  const env = process.env.VIBECHECK_SERVER_URL?.trim();
  if (env) return env;
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "VIBECHECK_SERVER_URL environment variable is required in production",
    );
  }
  return DEFAULT_DEV_BASE_URL;
}

function isAbortError(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  const name = (error as { name?: unknown }).name;
  return name === "AbortError" || name === "TimeoutError";
}

function combineSignals(
  upstream: AbortSignal | null,
  timeoutMs: number,
): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  if (!upstream) return timeoutSignal;
  if (typeof (AbortSignal as unknown as { any?: unknown }).any === "function") {
    return (
      AbortSignal as unknown as {
        any: (signals: AbortSignal[]) => AbortSignal;
      }
    ).any([upstream, timeoutSignal]);
  }
  const controller = new AbortController();
  const onAbort = (reason: unknown) => controller.abort(reason);
  if (upstream.aborted) controller.abort(upstream.reason);
  else upstream.addEventListener("abort", () => onAbort(upstream.reason));
  if (timeoutSignal.aborted) controller.abort(timeoutSignal.reason);
  else
    timeoutSignal.addEventListener("abort", () => onAbort(timeoutSignal.reason));
  return controller.signal;
}

async function fetchWithRetry(
  request: Request,
  attempts = FETCH_MAX_ATTEMPTS,
): Promise<Response> {
  const timeoutMs = timeoutForRequest(request);
  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt++) {
    const perAttempt = request.clone();
    try {
      return await fetch(
        new Request(perAttempt, {
          signal: combineSignals(request.signal, timeoutMs),
        }),
      );
    } catch (error) {
      if (isAbortError(error)) throw error;
      lastError = error;
      if (attempt === attempts - 1) break;
      const delay = FETCH_RETRY_BASE_DELAY_MS * 2 ** attempt;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error(String(lastError));
}

async function requestBackendJson<T>(
  path: string,
  options: {
    method: string;
    body?: unknown;
    headers?: HeadersInit;
  },
): Promise<{ data: T; response: Response }> {
  const baseUrl = resolveBaseUrl();
  const isProduction = process.env.NODE_ENV === "production";
  const headers = new Headers(options.headers);
  if (options.body !== undefined) {
    headers.set("content-type", "application/json");
  }

  let request = new Request(new URL(path, baseUrl), {
    method: options.method,
    headers,
    body:
      options.body === undefined
        ? undefined
        : JSON.stringify(options.body),
  });
  if (isProduction) {
    try {
      const token = await getAuthorizationHeader(baseUrl);
      if (token) {
        const authHeaders = new Headers(request.headers);
        authHeaders.set("Authorization", token);
        request = new Request(request, { headers: authHeaders });
      }
    } catch (error) {
      throw new VibecheckApiError(
        `Failed to fetch identity token: ${error instanceof Error ? error.message : String(error)}`,
        503,
      );
    }
  }

  let response: Response;
  try {
    response = await fetchWithRetry(request);
  } catch (error) {
    normalizeTransportError(error, `${options.method} ${path}`);
  }
  const body = await response.text();
  let parsed: unknown = null;
  if (body) {
    try {
      parsed = JSON.parse(body);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const errorBody = parseErrorBody(parsed);
    const codeFragment = errorBody?.error_code ?? "unknown";
    throw new VibecheckApiError(
      `vibecheck ${options.method} ${path} failed (${codeFragment})`,
      response.status,
      errorBody,
      response.headers,
    );
  }
  if (parsed === null) {
    throw new VibecheckApiError(
      `vibecheck ${options.method} ${path} returned empty body`,
      response.status,
      { error_code: "upstream_error", message: "Empty response body" },
      response.headers,
    );
  }
  return { data: parsed as T, response };
}

export async function uploadPdfToSignedUrl(
  uploadUrl: string,
  file: File,
): Promise<void> {
  let request = new Request(uploadUrl, {
    method: "PUT",
    headers: {
      "content-type": "application/pdf",
      // Browser-side fetch uses the File's type by default; explicitly setting this
      // header for backend consistency and to match the expected contract.
    },
    body: file,
  });

  let response: Response;
  try {
    response = await fetchWithRetry(request);
  } catch (error) {
    normalizeTransportError(error, "PUT to PDF upload URL");
  }
  if (!response.ok) {
    throw new VibecheckApiError(
      "PDF upload to signed URL failed",
      response.status,
      parseErrorBody(await response.text().catch(() => "")),
      response.headers,
    );
  }
}

export async function requestPdfUploadUrl(): Promise<UploadPdfResponse> {
  const { data, response } = await requestBackendJson<UploadPdfResponse>(
    "/api/upload-pdf",
    { method: "POST" },
  );
  const responsePayload = data as Partial<UploadPdfResponse>;
  if (
    typeof responsePayload.gcs_key !== "string" ||
    typeof responsePayload.upload_url !== "string"
  ) {
    throw new VibecheckApiError(
      "vibecheck /api/upload-pdf returned malformed payload",
      response.status,
      { error_code: "upstream_error", message: "Malformed upload response" },
      response.headers,
    );
  }
  return responsePayload as UploadPdfResponse;
}

export async function requestPdfAnalysis(
  gcsKey: string,
  filename: string,
): Promise<AnalyzeResponse> {
  const { data, response } = await requestBackendJson<AnalyzeResponse>(
    "/api/analyze-pdf",
    {
      method: "POST",
      body: { gcs_key: gcsKey, filename },
    },
  );
  const responsePayload = data as Partial<AnalyzeResponse>;
  if (
    typeof responsePayload.job_id !== "string" ||
    typeof responsePayload.status !== "string"
  ) {
    throw new VibecheckApiError(
      "vibecheck /api/analyze-pdf returned malformed payload",
      response.status,
      { error_code: "upstream_error", message: "Malformed analyze response" },
      response.headers,
    );
  }
  return responsePayload as AnalyzeResponse;
}

export function getClient() {
  const isProduction = process.env.NODE_ENV === "production";
  const baseUrl = resolveBaseUrl();

  return createClient<paths>({
    baseUrl,
    fetch: async (request: Request) => {
      if (isProduction) {
        try {
          const token = await getAuthorizationHeader(baseUrl);
          if (token) {
            const headers = new Headers(request.headers);
            headers.set("Authorization", token);
            request = new Request(request, { headers });
          }
        } catch (error) {
          throw new VibecheckApiError(
            `Failed to fetch identity token: ${error instanceof Error ? error.message : String(error)}`,
            503,
          );
        }
      }
      return fetchWithRetry(request);
    },
  });
}

function parseErrorBody(candidate: unknown): ApiErrorBody | null {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return null;
  }
  const raw = candidate as Record<string, unknown>;
  const body: ApiErrorBody = {};
  const code = clampErrorCode(raw.error_code);
  if (code) body.error_code = code;
  if (typeof raw.message === "string") body.message = raw.message;
  if (typeof raw.error_host === "string") body.error_host = raw.error_host;
  if (Object.keys(body).length === 0) {
    const detail = raw.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const nested = detail as Record<string, unknown>;
      const nestedCode = clampErrorCode(nested.error_code);
      if (nestedCode) body.error_code = nestedCode;
      if (typeof nested.message === "string") body.message = nested.message;
      if (typeof nested.error_host === "string")
        body.error_host = nested.error_host;
    }
  }
  return Object.keys(body).length > 0 ? body : null;
}

function normalizeTransportError(err: unknown, context: string): never {
  if (err instanceof VibecheckApiError) throw err;
  const message = err instanceof Error ? err.message : String(err);
  throw new VibecheckApiError(
    `vibecheck ${context} transport failure: ${message}`,
    503,
    { error_code: "upstream_error", message },
  );
}

export async function analyzeUrl(targetUrl: string): Promise<AnalyzeResponse> {
  let result;
  try {
    const client = getClient();
    result = await client.POST("/api/analyze", {
      body: { url: targetUrl },
    });
  } catch (err: unknown) {
    normalizeTransportError(err, "/api/analyze");
  }
  const { data, error, response } = result;
  if (error || !data) {
    const errorBody = parseErrorBody(error);
    const codeFragment = errorBody?.error_code ?? "unknown";
    throw new VibecheckApiError(
      `vibecheck /api/analyze failed (${codeFragment})`,
      response?.status ?? 500,
      errorBody,
      response?.headers ?? null,
    );
  }
  return data;
}

export async function pollJob(
  jobId: string,
  options?: { signal?: AbortSignal },
): Promise<JobState> {
  let result;
  try {
    const client = getClient();
    result = await client.GET("/api/analyze/{job_id}", {
      params: { path: { job_id: jobId } },
      signal: options?.signal,
    });
  } catch (err: unknown) {
    normalizeTransportError(err, `GET /api/analyze/${jobId}`);
  }
  const { data, error, response } = result;
  if (error || !data) {
    const errorBody = parseErrorBody(error);
    throw new VibecheckApiError(
      `vibecheck GET /api/analyze/${jobId} failed`,
      response?.status ?? 500,
      errorBody,
      response?.headers ?? null,
    );
  }
  return data;
}

export async function retrySection(
  jobId: string,
  slug: SectionSlug,
): Promise<RetryResponse> {
  let result;
  try {
    const client = getClient();
    result = await client.POST("/api/analyze/{job_id}/retry/{slug}", {
      params: { path: { job_id: jobId, slug } },
    });
  } catch (err: unknown) {
    normalizeTransportError(err, `retry ${slug} on ${jobId}`);
  }
  const { data, error, response } = result;
  if (error || !data) {
    const errorBody = parseErrorBody(error);
    throw new VibecheckApiError(
      `vibecheck retry ${slug} on ${jobId} failed`,
      response?.status ?? 500,
      errorBody,
      response?.headers ?? null,
    );
  }
  return data;
}
