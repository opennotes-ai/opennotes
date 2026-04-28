import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";
import {
  ARCHIVE_FONT_CDN_URL,
  ARCHIVE_FONT_FAMILY,
} from "@opennotes/tokens/archive-fonts";

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
    expect(await response.text()).toContain("<html>hi</html>");
  });

  it("forwards job_id to the backend archive-preview route", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("<html>hi</html>", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com&job_id=11111111-1111-1111-1111-111111111111",
    );
    await GET(event);

    const backendUrl = fetchMock.mock.calls[0]?.[0] as URL;
    expect(backendUrl.searchParams.get("url")).toBe("https://example.com");
    expect(backendUrl.searchParams.get("job_id")).toBe(
      "11111111-1111-1111-1111-111111111111",
    );
  });

  it("omits job_id when the frontend request does not include one", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("<html>hi</html>", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
    );
    await GET(event);

    const backendUrl = fetchMock.mock.calls[0]?.[0] as URL;
    expect(backendUrl.searchParams.has("job_id")).toBe(false);
  });

  it("returns 400 application/json for non-http target URL", async () => {
    const event = buildEvent(
      "http://localhost:3000/api/archive-preview?url=javascript:alert(1)",
    );
    const response = await GET(event);

    expect(response.status).toBe(400);
    expect(response.headers.get("content-type")).toMatch(/^application\/json/);
  });

  describe("font fallback injection (TASK-1495.03)", () => {
    it("injects IBM Plex Sans Condensed style block before </head> on success", async () => {
      const upstream =
        "<html><head><title>X</title></head><body>hi</body></html>";
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(upstream, { status: 200 })),
      );

      const event = buildEvent(
        "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
      );
      const response = await GET(event);
      const body = await response.text();

      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toBe(
        "text/html; charset=utf-8",
      );
      expect(body).toContain(ARCHIVE_FONT_FAMILY);
      expect(body).toContain(ARCHIVE_FONT_CDN_URL);
      const styleIdx = body.indexOf(ARCHIVE_FONT_FAMILY);
      const headCloseIdx = body.indexOf("</head>");
      expect(styleIdx).toBeGreaterThan(-1);
      expect(headCloseIdx).toBeGreaterThan(-1);
      expect(styleIdx).toBeLessThan(headCloseIdx);
    });

    it("loads the IBM Plex Sans Condensed family inside the iframe document via @import", async () => {
      const upstream =
        "<html><head><title>X</title></head><body>hi</body></html>";
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(upstream, { status: 200 })),
      );

      const event = buildEvent(
        "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
      );
      const response = await GET(event);
      const body = await response.text();

      // The @import must come BEFORE the font-family rule (CSS @import rules
      // are only valid as the first rule of a stylesheet).
      const importIdx = body.indexOf(`@import url('${ARCHIVE_FONT_CDN_URL}')`);
      const familyIdx = body.indexOf(`font-family:${ARCHIVE_FONT_FAMILY}`);
      expect(importIdx).toBeGreaterThan(-1);
      expect(familyIdx).toBeGreaterThan(importIdx);
    });

    it("prepends the style block when upstream HTML has no </head>", async () => {
      const upstream = "<body>hi</body>";
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(upstream, { status: 200 })),
      );

      const event = buildEvent(
        "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
      );
      const response = await GET(event);
      const body = await response.text();

      expect(body.startsWith("<style>")).toBe(true);
      expect(body).toContain("'IBM Plex Sans Condensed'");
      expect(body).toContain("<body>hi</body>");
    });

    it("does not inject the font fallback into uppercase </HEAD> documents (lowercase-only by design)", async () => {
      const upstream =
        "<html><HEAD><title>X</title></HEAD><body>hi</body></html>";
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(upstream, { status: 200 })),
      );

      const event = buildEvent(
        "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
      );
      const response = await GET(event);
      const body = await response.text();

      expect(body.startsWith("<style>")).toBe(true);
      expect(body).toContain("'IBM Plex Sans Condensed'");
    });

    it("does not modify failure-path bodies (no font injection on 502)", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockRejectedValue(new Error("network down")),
      );

      const event = buildEvent(
        "http://localhost:3000/api/archive-preview?url=https%3A%2F%2Fexample.com",
      );
      const response = await GET(event);
      const body = await response.text();

      expect(response.status).toBe(502);
      expect(body).toBe("Archive unavailable");
      expect(body).not.toContain("IBM Plex Sans Condensed");
    });
  });
});
