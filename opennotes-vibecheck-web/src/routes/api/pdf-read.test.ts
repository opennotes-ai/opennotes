import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

const { getAuthorizationHeaderMock } = vi.hoisted(() => ({
  getAuthorizationHeaderMock: vi.fn(async () => null as string | null),
}));

vi.mock("~/lib/api-client.server", () => ({
  resolveBaseUrl: vi.fn(() => "http://backend.test"),
  getAuthorizationHeader: getAuthorizationHeaderMock,
}));

import { GET } from "./pdf-read";

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

describe("GET /api/pdf-read", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.unstubAllGlobals();
    getAuthorizationHeaderMock.mockReset();
    getAuthorizationHeaderMock.mockResolvedValue(null);
    delete process.env.NODE_ENV;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    globalThis.fetch = originalFetch;
    delete process.env.NODE_ENV;
  });

  it("rejects requests without a job_id", async () => {
    const response = await GET(buildEvent("http://localhost:3000/api/pdf-read"));

    expect(response.status).toBe(400);
    expect(response.headers.get("cache-control")).toBe("no-store, private");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await response.json()).toEqual({ detail: "job_id is required" });
  });

  it("forwards job_id to the backend pdf-read route without following redirects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: { location: "https://storage.example.com/signed.pdf" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      buildEvent(
        "http://localhost:3000/api/pdf-read?job_id=11111111-1111-1111-1111-111111111111",
      ),
    );

    const [backendUrl, init] = fetchMock.mock.calls[0] as [
      URL,
      RequestInit,
    ];
    expect(backendUrl.href).toBe(
      "http://backend.test/api/pdf-read?job_id=11111111-1111-1111-1111-111111111111",
    );
    expect(init.redirect).toBe("manual");
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://storage.example.com/signed.pdf",
    );
    expect(response.headers.get("cache-control")).toBe("no-store, private");
  });

  it("returns a controlled 503 when production auth acquisition fails", async () => {
    process.env.NODE_ENV = "production";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    getAuthorizationHeaderMock.mockRejectedValue(new Error("metadata down"));

    const response = await GET(
      buildEvent("http://localhost:3000/api/pdf-read?job_id=pdf-job"),
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("no-store, private");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await response.text()).toBe("PDF unavailable");
  });

  it("streams an upstream PDF response when the backend does not redirect", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("%PDF-1.4\n", {
          status: 200,
          headers: {
            "content-type": "application/pdf",
            "content-length": "9",
          },
        }),
      ),
    );

    const response = await GET(
      buildEvent("http://localhost:3000/api/pdf-read?job_id=pdf-job"),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(response.headers.get("content-length")).toBe("9");
    expect(await response.text()).toBe("%PDF-1.4\n");
  });

  it("returns 502 when the backend fetch throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down")),
    );

    const response = await GET(
      buildEvent("http://localhost:3000/api/pdf-read?job_id=pdf-job"),
    );

    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toMatch(/^text\/plain/);
    expect(await response.text()).toBe("PDF unavailable");
  });

  it("passes through upstream non-OK status with an empty text response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not found", { status: 404 })),
    );

    const response = await GET(
      buildEvent("http://localhost:3000/api/pdf-read?job_id=missing"),
    );

    expect(response.status).toBe(404);
    expect(response.headers.get("content-type")).toMatch(/^text\/plain/);
    expect(await response.text()).toBe("");
  });
});
