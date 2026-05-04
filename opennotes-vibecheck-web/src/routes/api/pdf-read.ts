import type { APIEvent } from "@solidjs/start/server";
import { getAuthorizationHeader, resolveBaseUrl } from "~/lib/api-client.server";

const PDF_HEADERS = {
  "cache-control": "no-store, private",
  "referrer-policy": "no-referrer",
};

function pdfError(message: string, status: number): Response {
  return new Response(message, {
    status,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      ...PDF_HEADERS,
    },
  });
}

function copyPdfHeaders(upstream: Response): Headers {
  const headers = new Headers(PDF_HEADERS);
  headers.set(
    "content-type",
    upstream.headers.get("content-type") ?? "application/pdf",
  );
  const contentLength = upstream.headers.get("content-length");
  if (contentLength) headers.set("content-length", contentLength);
  return headers;
}

export async function GET(event: APIEvent): Promise<Response> {
  const requestUrl = new URL(event.request.url);
  const jobId = requestUrl.searchParams.get("job_id");
  if (!jobId) {
    return Response.json(
      { detail: "job_id is required" },
      { status: 400, headers: PDF_HEADERS },
    );
  }

  const backendBase = resolveBaseUrl();
  const backendUrl = new URL("/api/pdf-read", backendBase);
  backendUrl.searchParams.set("job_id", jobId);

  const headers = new Headers();
  if (process.env.NODE_ENV === "production") {
    try {
      const auth = await getAuthorizationHeader(backendBase);
      if (auth) headers.set("Authorization", auth);
    } catch {
      return pdfError("PDF unavailable", 503);
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl, {
      headers,
      redirect: "manual",
      signal: event.request.signal,
    });
  } catch {
    return pdfError("PDF unavailable", 502);
  }

  if (upstream.status >= 300 && upstream.status < 400) {
    const location = upstream.headers.get("location");
    if (location) {
      return new Response(null, {
        status: upstream.status,
        headers: {
          location,
          ...PDF_HEADERS,
        },
      });
    }
  }

  if (!upstream.ok) {
    return pdfError("", upstream.status);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: copyPdfHeaders(upstream),
  });
}
