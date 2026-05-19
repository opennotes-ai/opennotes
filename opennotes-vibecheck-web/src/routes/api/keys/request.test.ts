import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

vi.mock("~/lib/api-client.server", () => ({
  resolveBaseUrl: vi.fn(() => "http://backend.test"),
  getAuthorizationHeader: vi.fn(async () => null),
}));

import { POST } from "./request";
import { getAuthorizationHeader } from "~/lib/api-client.server";

function buildEvent(options: { authorization?: string; body?: string } = {}): APIEvent {
  const headers = new Headers({ "content-type": "application/json" });
  if (options.authorization) headers.set("Authorization", options.authorization);
  const request = new Request("http://localhost:3000/api/keys/request", {
    method: "POST",
    headers,
    body: options.body ?? JSON.stringify({ email: "user@example.com" }),
  });
  return {
    request,
    params: {},
    nativeEvent: {} as unknown,
    locals: {},
    response: {} as unknown,
    fetch: globalThis.fetch,
    clientAddress: null,
  } as unknown as APIEvent;
}

describe("POST /api/keys/request", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(getAuthorizationHeader).mockResolvedValue(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    globalThis.fetch = originalFetch;
  });

  it("returns 502 application/json with upstream_error when upstream fetch throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    const response = await POST(buildEvent());

    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toMatch(/^application\/json/);
    const body = await response.json();
    expect(body.error_code).toBe("upstream_error");
  });

  it("passes through 200 with JSON body on success", async () => {
    const backendBody = JSON.stringify({ key: "vc_abc123", expires_at: "2026-06-01T00:00:00Z" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 200, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent());

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.key).toBe("vc_abc123");
  });

  it("forwards 400 invalid_email body verbatim so the extension can surface the message", async () => {
    const backendBody = JSON.stringify({ error_code: "invalid_email", message: "Email is not valid" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 400, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent({ body: JSON.stringify({ email: "notanemail" }) }));

    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.error_code).toBe("invalid_email");
    expect(body.message).toBe("Email is not valid");
  });

  it("returns 502 with upstream_error when backend responds 5xx", async () => {
    const backendBody = JSON.stringify({ detail: "Internal Server Error" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 500, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent());

    expect(response.status).toBe(500);
  });

  it("does NOT forward incoming Authorization header to the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ key: "vc_x" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent({ authorization: "Bearer user-auth-token" }));

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.has("Authorization")).toBe(false);
  });

  it("sets X-Serverless-Authorization when getAuthorizationHeader returns a token", async () => {
    vi.mocked(getAuthorizationHeader).mockResolvedValue("Bearer goog-id-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ key: "vc_x" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent());

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.get("X-Serverless-Authorization")).toBe("Bearer goog-id-token");
    expect(callHeaders.has("Authorization")).toBe(false);
  });

  it("does not set X-Serverless-Authorization when getAuthorizationHeader returns null", async () => {
    vi.mocked(getAuthorizationHeader).mockResolvedValue(null);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ key: "vc_x" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent());

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.has("X-Serverless-Authorization")).toBe(false);
  });

  it("returns 502 application/json with upstream_error when getAuthorizationHeader throws", async () => {
    vi.mocked(getAuthorizationHeader).mockRejectedValue(new Error("identity token fetch timed out"));
    vi.stubGlobal("fetch", vi.fn());

    const response = await POST(buildEvent());

    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toMatch(/^application\/json/);
    const body = await response.json();
    expect(body.error_code).toBe("upstream_error");
  });

  it("forwards request body to the backend unchanged", async () => {
    const requestBody = JSON.stringify({ email: "test@example.com" });
    let capturedBody = "";
    const fetchMock = vi.fn().mockImplementation(async (_url: unknown, init: RequestInit) => {
      capturedBody = init.body as string;
      return new Response(JSON.stringify({ key: "vc_x" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent({ body: requestBody }));

    expect(capturedBody).toBe(requestBody);
  });

  it("routes the request to /api/keys/request on the backend", async () => {
    let capturedUrl = "";
    const fetchMock = vi.fn().mockImplementation(async (url: unknown) => {
      capturedUrl = url instanceof URL ? url.toString() : String(url);
      return new Response(JSON.stringify({ key: "vc_x" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent());

    expect(capturedUrl).toBe("http://backend.test/api/keys/request");
  });
});
