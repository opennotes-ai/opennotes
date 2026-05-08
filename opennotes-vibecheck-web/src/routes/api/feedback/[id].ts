import type { APIEvent } from "@solidjs/start/server";
import { getAuthorizationHeader, resolveBaseUrl } from "~/lib/api-client.server";

export async function PATCH(event: APIEvent): Promise<Response> {
  let response: Response;
  try {
    const backendBase = resolveBaseUrl();
    const id = event.params.id as string;
    const backendUrl = new URL(`/api/feedback/${id}`, backendBase);

    const headers = new Headers();
    headers.set("content-type", "application/json");

    const incomingCookie = event.request.headers.get("cookie");
    if (incomingCookie) headers.set("cookie", incomingCookie);

    const idToken = await getAuthorizationHeader(backendBase);
    if (idToken) headers.set("X-Serverless-Authorization", idToken);

    response = await fetch(backendUrl, {
      method: "PATCH",
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
  const responseHeaders = new Headers({ "content-type": contentType });
  for (const value of response.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", value);
  }
  return new Response(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}
