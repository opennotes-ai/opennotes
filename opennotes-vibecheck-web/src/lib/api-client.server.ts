import createClient from "openapi-fetch";
import { GoogleAuth } from "google-auth-library";
import type { IdTokenClient } from "google-auth-library";
import type { paths, components } from "./generated-types";

export type SidebarPayload = components["schemas"]["SidebarPayload"];

const FETCH_TIMEOUT_MS = 540_000;
const FETCH_MAX_ATTEMPTS = 2;
const FETCH_RETRY_BASE_DELAY_MS = 250;
const IDENTITY_TOKEN_MAX_RETRIES = 3;
const TOKEN_FETCH_TIMEOUT_MS = 5_000;
const DEFAULT_DEV_BASE_URL = "http://localhost:8000";

export class VibecheckApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
  ) {
    super(message);
    this.name = "VibecheckApiError";
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

export async function analyzeUrl(targetUrl: string): Promise<SidebarPayload> {
  const client = getClient();
  const { data, error, response } = await client.POST("/api/analyze", {
    body: { url: targetUrl },
  });
  if (error || !data) {
    throw new VibecheckApiError(
      `vibecheck /api/analyze failed: ${error ? JSON.stringify(error) : "empty response body"}`,
      response?.status ?? 500,
    );
  }
  return data;
}
