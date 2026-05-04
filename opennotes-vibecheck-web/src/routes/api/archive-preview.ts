import type { APIEvent } from "@solidjs/start/server";
import {
  ARCHIVE_FONT_CDN_URL,
  ARCHIVE_FONT_FAMILY,
} from "@opennotes/tokens/archive-fonts";
import { getAuthorizationHeader, resolveBaseUrl } from "~/lib/api-client.server";

const ARCHIVE_CSP =
  "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; " +
  "font-src https: data:; frame-src 'none'; form-action 'none'; base-uri 'none'; " +
  "frame-ancestors 'self'";

const ARCHIVE_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "no-store, private",
  "content-security-policy": ARCHIVE_CSP,
  "referrer-policy": "no-referrer",
};

function injectFontFallback(html: string): string {
  const style =
    `<style>` +
    `@import url('${ARCHIVE_FONT_CDN_URL}');` +
    `html,body{font-family:${ARCHIVE_FONT_FAMILY},system-ui,sans-serif;}` +
    `</style>`;
  if (html.includes("</head>")) {
    return html.replace("</head>", `${style}</head>`);
  }
  return style + html;
}

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
  const sourceType = requestUrl.searchParams.get("source_type");
  const targetUrl = requestUrl.searchParams.get("url") ?? "";
  const jobId = requestUrl.searchParams.get("job_id");
  if (sourceType !== "pdf" && !isHttpUrl(targetUrl)) {
    return Response.json({ detail: "URL must be an http(s) URL" }, { status: 400 });
  }
  if (sourceType === "pdf" && !jobId) {
    return Response.json({ detail: "job_id is required" }, { status: 400 });
  }

  const backendBase = resolveBaseUrl();
  const backendUrl = new URL("/api/archive-preview", backendBase);
  if (sourceType === "pdf") {
    backendUrl.searchParams.set("source_type", "pdf");
  } else {
    backendUrl.searchParams.set("url", targetUrl);
  }
  if (jobId) backendUrl.searchParams.set("job_id", jobId);

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
    return new Response("Archive unavailable", {
      status: 502,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store, private",
      },
    });
  }

  if (!response.ok) {
    return new Response("", {
      status: response.status,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store, private",
      },
    });
  }

  const upstreamHtml = await response.text();
  return new Response(injectFontFallback(upstreamHtml), {
    status: 200,
    headers: ARCHIVE_HEADERS,
  });
}
