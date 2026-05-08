import type { APIEvent } from "@solidjs/start/server";
import { getAuthorizationHeader, resolveBaseUrl } from "~/lib/api-client.server";

export async function POST(event: APIEvent): Promise<Response> {
  let response: Response;
  try {
    const backendBase = resolveBaseUrl();
    const backendUrl = new URL("/api/feedback", backendBase);

    const headers = new Headers();
    headers.set("content-type", "application/json");

    const incomingCookie = event.request.headers.get("cookie");
    if (incomingCookie) headers.set("cookie", incomingCookie);

    const idToken = await getAuthorizationHeader(backendBase);
    if (idToken) headers.set("X-Serverless-Authorization", idToken);

    response = await fetch(backendUrl, {
      method: "POST",
      headers,
      body: await event.request.text(),
      signal: event.request.signal,
    });
  } catch {
    return Response.json(
      { error_code: "upstream_error", message: "upstream unavailable" },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  responseHeaders.set(
    "content-type",
    response.headers.get("content-type") ?? "application/json",
  );
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) responseHeaders.set("set-cookie", setCookie);

  return new Response(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}
