import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

vi.mock("~/lib/api-client.server", () => ({
  resolveBaseUrl: vi.fn(() => "http://backend.test"),
  getAuthorizationHeader: vi.fn(async () => null),
}));

import { POST } from "./index";
import { getAuthorizationHeader } from "~/lib/api-client.server";

function buildEvent(options: {
  body?: string;
  cookie?: string;
} = {}): APIEvent {
  const headers = new Headers({ "content-type": "application/json" });
  if (options.cookie) headers.set("cookie", options.cookie);
  const request = new Request("http://localhost:3000/api/feedback", {
    method: "POST",
    headers,
    body: options.body ?? JSON.stringify({ page_path: "/analyze" }),
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

describe("POST /api/feedback", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(getAuthorizationHeader).mockResolvedValue(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    globalThis.fetch = originalFetch;
  });

  it("returns 502 with upstream_error when upstream fetch throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    const response = await POST(buildEvent());

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.error_code).toBe("upstream_error");
  });

  it("passes through 201 with JSON body on success", async () => {
    const backendBody = JSON.stringify({ id: "feedback-uuid" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(backendBody, { status: 201, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(buildEvent());

    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body.id).toBe("feedback-uuid");
  });

  it("forwards incoming cookie header to upstream", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "x" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent({ cookie: "uid=abc123; session=xyz" }));

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.get("cookie")).toBe("uid=abc123; session=xyz");
  });

  it("forwards multiple Set-Cookie headers as separate values (not comma-collapsed)", async () => {
    const upstreamHeaders = new Headers();
    upstreamHeaders.append("content-type", "application/json");
    upstreamHeaders.append("set-cookie", "uid=abc123; Path=/; HttpOnly; SameSite=Lax; Expires=Thu, 01 Jan 2026 00:00:00 GMT");
    upstreamHeaders.append("set-cookie", "session=xyz789; Path=/; HttpOnly; SameSite=Lax");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: "x" }), { status: 201, headers: upstreamHeaders }),
      ),
    );

    const response = await POST(buildEvent());

    const setCookieValues = response.headers.getSetCookie();
    expect(setCookieValues).toHaveLength(2);
    expect(setCookieValues[0]).toContain("uid=abc123");
    expect(setCookieValues[0]).toContain("Expires=");
    expect(setCookieValues[1]).toContain("session=xyz789");
  });

  it("does not corrupt cookies that contain commas in expires= attribute", async () => {
    const cookieWithCommaExpires =
      "uid=abc123; Path=/; HttpOnly; Expires=Thu, 01 Jan 2026 00:00:00 GMT";
    const secondCookie = "session=xyz; Path=/; HttpOnly";

    const upstreamHeaders = new Headers();
    upstreamHeaders.append("content-type", "application/json");
    upstreamHeaders.append("set-cookie", cookieWithCommaExpires);
    upstreamHeaders.append("set-cookie", secondCookie);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: "x" }), { status: 201, headers: upstreamHeaders }),
      ),
    );

    const response = await POST(buildEvent());

    const setCookieValues = response.headers.getSetCookie();
    expect(setCookieValues).toHaveLength(2);
    expect(setCookieValues[0]).toBe(cookieWithCommaExpires);
    expect(setCookieValues[1]).toBe(secondCookie);
  });

  it("returns 502 when getAuthorizationHeader throws", async () => {
    vi.mocked(getAuthorizationHeader).mockRejectedValue(new Error("identity token fetch timed out"));
    vi.stubGlobal("fetch", vi.fn());

    const response = await POST(buildEvent());

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.error_code).toBe("upstream_error");
  });

  it("sets X-Serverless-Authorization when getAuthorizationHeader returns a token", async () => {
    vi.mocked(getAuthorizationHeader).mockResolvedValue("Bearer goog-id-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "x" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(buildEvent());

    const callHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(callHeaders.get("X-Serverless-Authorization")).toBe("Bearer goog-id-token");
  });
});
