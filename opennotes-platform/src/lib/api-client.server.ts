import { GoogleAuth } from "google-auth-library";

const FETCH_TIMEOUT_MS = 10_000;

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

function getAuthInstance(): GoogleAuth {
  if (!authInstance) authInstance = new GoogleAuth();
  return authInstance;
}

async function getAuthorizationHeader(
  targetAudience: string,
): Promise<string | null> {
  if (process.env.NODE_ENV !== "production") return null;
  const auth = getAuthInstance();
  const client = await auth.getIdTokenClient(targetAudience);
  const headers = await client.getRequestHeaders();
  return headers.get("Authorization") || null;
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
  await apiFetch(`/api/v2/admin/api-keys/${keyId}`, { method: "DELETE" });
}
