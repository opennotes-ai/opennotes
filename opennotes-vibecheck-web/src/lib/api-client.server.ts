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

export interface ApiErrorBody {
  error_code?: string;
  message?: string;
  error_host?: string;
}

const FETCH_TIMEOUT_MS = 540_000;
const FETCH_MAX_ATTEMPTS = 2;
const FETCH_RETRY_BASE_DELAY_MS = 250;
const IDENTITY_TOKEN_MAX_RETRIES = 3;
const TOKEN_FETCH_TIMEOUT_MS = 5_000;
const DEFAULT_DEV_BASE_URL = "http://localhost:8000";

export class VibecheckApiError extends Error {
  public errorBody: ApiErrorBody | null;

  constructor(
    message: string,
    public statusCode: number,
    errorBody: ApiErrorBody | null = null,
  ) {
    super(message);
    this.name = "VibecheckApiError";
    this.errorBody = errorBody;
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
          const headers = await client.getRequestHeaders();
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

function resolveBaseUrl(): string {
  const env = process.env.VIBECHECK_SERVER_URL?.trim();
  if (env) return env;
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "VIBECHECK_SERVER_URL environment variable is required in production",
    );
  }
  return DEFAULT_DEV_BASE_URL;
}

async function fetchWithRetry(
  request: Request,
  attempts = FETCH_MAX_ATTEMPTS,
): Promise<Response> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt++) {
    const perAttempt = request.clone();
    try {
      return await fetch(
        new Request(perAttempt, {
          signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
        }),
      );
    } catch (error) {
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
  if (!candidate || typeof candidate !== "object") return null;
  const raw = candidate as Record<string, unknown>;
  const body: ApiErrorBody = {};
  if (typeof raw.error_code === "string") body.error_code = raw.error_code;
  if (typeof raw.message === "string") body.message = raw.message;
  if (typeof raw.error_host === "string") body.error_host = raw.error_host;
  return Object.keys(body).length > 0 ? body : null;
}

export async function analyzeUrl(targetUrl: string): Promise<AnalyzeResponse> {
  const client = getClient();
  const { data, error, response } = await client.POST("/api/analyze", {
    body: { url: targetUrl },
  });
  if (error || !data) {
    const errorBody = parseErrorBody(error);
    const codeFragment = errorBody?.error_code ?? "unknown";
    throw new VibecheckApiError(
      `vibecheck /api/analyze failed (${codeFragment})`,
      response?.status ?? 500,
      errorBody,
    );
  }
  return data;
}

export async function pollJob(jobId: string): Promise<JobState> {
  const client = getClient();
  const { data, error, response } = await client.GET("/api/analyze/{job_id}", {
    params: { path: { job_id: jobId } },
  });
  if (error || !data) {
    const errorBody = parseErrorBody(error);
    throw new VibecheckApiError(
      `vibecheck GET /api/analyze/${jobId} failed`,
      response?.status ?? 500,
      errorBody,
    );
  }
  return data;
}

export async function retrySection(
  jobId: string,
  slug: SectionSlug,
): Promise<RetryResponse> {
  const client = getClient();
  const { data, error, response } = await client.POST(
    "/api/analyze/{job_id}/retry/{slug}",
    { params: { path: { job_id: jobId, slug } } },
  );
  if (error || !data) {
    const errorBody = parseErrorBody(error);
    throw new VibecheckApiError(
      `vibecheck retry ${slug} on ${jobId} failed`,
      response?.status ?? 500,
      errorBody,
    );
  }
  return data;
}
