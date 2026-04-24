import type { APIEvent } from "@solidjs/start/server";
import { getAuthorizationHeader, resolveBaseUrl } from "~/lib/api-client.server";

const ARCHIVE_CSP =
  "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; " +
  "font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; " +
  "frame-ancestors 'self'";

const ARCHIVE_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "no-store, private",
  "content-security-policy": ARCHIVE_CSP,
};

function isHttpUrl(candidate: string): boolean {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export async function GET(event: APIEvent): Promise<Response> {
  const requestUrl = new URL(event.request.url);
  const targetUrl = requestUrl.searchParams.get("url") ?? "";
  if (!isHttpUrl(targetUrl)) {
    return Response.json({ detail: "URL must be an http(s) URL" }, { status: 400 });
  }

  const backendBase = resolveBaseUrl();
  const backendUrl = new URL("/api/archive-preview", backendBase);
  backendUrl.searchParams.set("url", targetUrl);

  const headers = new Headers();
  if (process.env.NODE_ENV === "production") {
    const auth = await getAuthorizationHeader(backendBase);
    if (auth) headers.set("Authorization", auth);
  }

  let response: Response;
  try {
    response = await fetch(backendUrl, {
      headers,
      signal: event.request.signal,
    });
  } catch {
    return Response.json({ detail: "Archive unavailable" }, { status: 502 });
  }

  if (!response.ok) {
    return new Response("", {
      status: response.status,
      headers: ARCHIVE_HEADERS,
    });
  }

  return new Response(await response.text(), {
    status: 200,
    headers: ARCHIVE_HEADERS,
  });
}
