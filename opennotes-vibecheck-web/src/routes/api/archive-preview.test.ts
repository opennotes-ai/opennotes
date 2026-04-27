import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

vi.mock("~/lib/api-client.server", () => ({
  resolveBaseUrl: vi.fn(() => "http://backend.test"),
  getAuthorizationHeader: vi.fn(async () => null),
}));

import { GET } from "./archive-preview";

function buildEvent(url: string): APIEvent {
  const request = new Request(url);
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

describe("GET /api/archive-preview", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    globalThis.fetch = originalFetch;
  });

  it("returns 502 text/plain 'Archive unavailable' when upstream fetch throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down")),
    );

    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
    );
    const response = await GET(event);

    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toMatch(/^text\/plain/);
    expect(await response.text()).toBe("Archive unavailable");
  });

  it("passes through upstream non-OK status with text/plain and empty body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 404 })),
    );

    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
    );
    const response = await GET(event);

    expect(response.status).toBe(404);
    expect(response.headers.get("content-type")).toMatch(/^text\/plain/);
    expect(await response.text()).toBe("");
  });

  it("returns 200 text/html with CSP and upstream body when upstream is OK", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(new Response("<html>hi</html>", { status: 200 })),
    );

    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
    );
    const response = await GET(event);

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe(
      "text/html; charset=utf-8",
    );
    const csp = response.headers.get("content-security-policy");
    expect(csp).toBeTruthy();
    expect(csp).toContain("default-src 'none'");
    expect(await response.text()).toBe("<html>hi</html>");
  });

  it("returns 400 application/json for non-http target URL", async () => {
    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=javascript:alert(1)",
    );
    const response = await GET(event);

    expect(response.status).toBe(400);
    expect(response.headers.get("content-type")).toMatch(/^application\/json/);
  });
});
