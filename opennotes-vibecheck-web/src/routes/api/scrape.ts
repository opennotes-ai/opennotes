import type { APIEvent } from "@solidjs/start/server";
import { getAuthorizationHeader, resolveBaseUrl } from "~/lib/api-client.server";

export async function POST(event: APIEvent): Promise<Response> {
  let response: Response;
  try {
    const backendBase = resolveBaseUrl();
    const backendUrl = new URL("/api/scrape", backendBase);

    const headers = new Headers();
    headers.set("content-type", "application/json");

    const incomingAuth = event.request.headers.get("Authorization");
    if (incomingAuth) headers.set("Authorization", incomingAuth);

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

  const contentType = response.headers.get("content-type") ?? "application/json";
  return new Response(response.body, {
    status: response.status,
    headers: { "content-type": contentType },
  });
}
