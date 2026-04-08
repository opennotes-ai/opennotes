import { GoogleAuth } from "google-auth-library";
import type { IdTokenClient } from "google-auth-library";

const FETCH_TIMEOUT_MS = 10_000;
const IDENTITY_TOKEN_MAX_RETRIES = 3;
const TOKEN_FETCH_TIMEOUT_MS = 5_000;

export class PlatformApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
  ) {
    super(message);
    this.name = "PlatformApiError";
  }
}

let authInstance: GoogleAuth | null = null;
const idTokenClientCache = new Map<string, IdTokenClient>();

function getAuthInstance(): GoogleAuth {
  if (!authInstance) authInstance = new GoogleAuth();
  return authInstance;
}

async function getAuthorizationHeader(
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
          await new Promise((r) => setTimeout(r, 100 * 2 ** attempt));
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

function getBaseConfig() {
  const isProduction = process.env.NODE_ENV === "production";
  const baseUrl =
    process.env.OPENNOTES_SERVER_URL ||
    (isProduction ? undefined : "http://localhost:8000");
  const apiKey = process.env.OPENNOTES_API_KEY?.trim() || "";
  if (isProduction && (!baseUrl || !apiKey)) {
    throw new PlatformApiError(
      "Server configuration missing in production",
      503,
    );
  }
  return { baseUrl: baseUrl!, apiKey, isProduction };
}

async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const { baseUrl, apiKey, isProduction } = getBaseConfig();
  const headers = new Headers(options.headers);
  headers.set("X-API-Key", apiKey);
  headers.set("Content-Type", "application/json");

  if (isProduction) {
    const token = await getAuthorizationHeader(baseUrl);
    if (token) headers.set("Authorization", token);
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new PlatformApiError(
      `API error ${response.status}: ${body}`,
      response.status,
    );
  }
  return response;
}

export interface AdminAPIKey {
  id: string;
  name: string;
  key: string;
  key_prefix?: string;
  scopes: string[] | null;
  user_email: string;
  user_display_name: string;
  created_at: string;
  expires_at: string | null;
  is_active?: boolean;
}

export interface CreateKeyRequest {
  user_email: string;
  user_display_name: string;
  key_name: string;
  scopes: string[];
}

export async function createAdminApiKey(
  data: CreateKeyRequest,
): Promise<AdminAPIKey> {
  const response = await apiFetch("/api/v2/admin/api-keys", {
    method: "POST",
    body: JSON.stringify(data),
  });
  return response.json();
}

export async function listAdminApiKeys(): Promise<AdminAPIKey[]> {
  const response = await apiFetch("/api/v2/admin/api-keys");
  return response.json();
}

export async function revokeAdminApiKey(keyId: string): Promise<void> {
  const uuidRegex =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!uuidRegex.test(keyId)) {
    throw new PlatformApiError("Invalid key ID format", 400);
  }
  await apiFetch(`/api/v2/admin/api-keys/${keyId}`, { method: "DELETE" });
}
