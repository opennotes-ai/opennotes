import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

vi.mock("~/lib/api-client.server", () => ({
  resolveBaseUrl: vi.fn(() => "http://backend.test"),
  getAuthorizationHeader: vi.fn(async () => null),
}));

import { POST } from "./scrape";
import { getAuthorizationHeader } from "~/lib/api-client.server";

function buildEvent(options: { authorization?: string; body?: string } = {}): APIEvent {
  const headers = new Headers({ "content-type": "application/json" });
  if (options.authorization) headers.set("Authorization", options.authorization);
  const request = new Request("http://localhost:3000/api/scrape", {
    method: "POST",
    headers,
    body: options.body ?? JSON.stringify({ url: "https://example.com", html: "<html>" }),
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

describe("POST /api/scrape", () => {
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

    const response = await POST(buildEvent({ authorization: "Bearer valid-token" }));

    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toMatch(/^application\/json/);
    const body = await response.json();
    expect(body.error_code).toBe("upstream_error");
  });

  it("passes through 201 with JSON body on success", async () => {
    const backendBody = JSON.stringify({ job_id: "abc-123", analyze_url: "/jobs/abc-123" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 201, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent({ authorization: "Bearer valid-token" }));

    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body.job_id).toBe("abc-123");
    expect(body.analyze_url).toBe("/jobs/abc-123");
  });

  it("passes through 401 when backend rejects the scrape token", async () => {
    const backendBody = JSON.stringify({ error_code: "unauthorized", message: "bad token" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 401, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent({ authorization: "Bearer wrong-token" }));

    expect(response.status).toBe(401);
    const body = await response.json();
    expect(body.error_code).toBe("unauthorized");
  });

  it("passes through non-2xx backend responses with original status", async () => {
    const backendBody = JSON.stringify({ error_code: "invalid_url", message: "bad url" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 400, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent({ authorization: "Bearer valid-token" }));

    expect(response.status).toBe(400);
  });

  it("forwards the incoming Authorization header to the backend fetch call", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: "x", analyze_url: "/j" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent({ authorization: "Bearer my-scrape-token" }));

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.get("Authorization")).toBe("Bearer my-scrape-token");
  });

  it("sets X-Serverless-Authorization when getAuthorizationHeader returns a token", async () => {
    vi.mocked(getAuthorizationHeader).mockResolvedValue("Bearer goog-id-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: "x", analyze_url: "/j" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent({ authorization: "Bearer my-scrape-token" }));

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.get("X-Serverless-Authorization")).toBe("Bearer goog-id-token");
    expect(callHeaders.get("Authorization")).toBe("Bearer my-scrape-token");
  });

  it("does not set X-Serverless-Authorization when getAuthorizationHeader returns null", async () => {
    vi.mocked(getAuthorizationHeader).mockResolvedValue(null);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: "x", analyze_url: "/j" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent({ authorization: "Bearer my-scrape-token" }));

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.has("X-Serverless-Authorization")).toBe(false);
  });
});
