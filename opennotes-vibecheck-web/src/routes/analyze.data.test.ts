import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const { analyzeUrlMock, retrySectionMock, clientGetMock } = vi.hoisted(() => ({
  analyzeUrlMock: vi.fn(),
  retrySectionMock: vi.fn(),
  clientGetMock: vi.fn(),
}));

vi.mock("~/lib/api-client.server", async () => {
  const actual = await vi.importActual<
    typeof import("~/lib/api-client.server")
  >("~/lib/api-client.server");
  return {
    ...actual,
    analyzeUrl: analyzeUrlMock,
    retrySection: retrySectionMock,
    getClient: () => ({ GET: clientGetMock, POST: vi.fn() }),
  };
});

async function callAction(url: string): Promise<Response> {
  const { resolveAnalyzeRedirect } = await import("./analyze.data");
  const fd = new FormData();
  fd.set("url", url);
  try {
    await resolveAnalyzeRedirect(fd);
    throw new Error("resolveAnalyzeRedirect did not redirect");
  } catch (thrown) {
    if (thrown instanceof Response) return thrown;
    throw thrown;
  }
}

describe("analyzeAction", () => {
  beforeEach(() => {
    analyzeUrlMock.mockReset();
    retrySectionMock.mockReset();
    clientGetMock.mockReset();
    vi.resetModules();
  });

  it("invalid URL redirects to /?error=invalid_url", async () => {
    const response = await callAction("not-a-url");
    expect(response.status).toBeGreaterThanOrEqual(300);
    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
    expect(analyzeUrlMock).not.toHaveBeenCalled();
  });

  it("successful POST redirects to /analyze?job=<id>", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-abc",
      status: "pending",
      cached: false,
    });
    const response = await callAction("https://example.com/p");
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("/analyze?job=job-abc");
    expect(location).not.toContain("c=1");
  });

  it("cached=true adds &c=1 to the redirect", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-cached",
      status: "done",
      cached: true,
    });
    const response = await callAction("https://example.com/p");
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("job=job-cached");
    expect(location).toContain("c=1");
  });

  it("422 unsupported_site redirects to /analyze?pending_error=unsupported_site&url=&host=", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("unsupported_site", 422, {
        error_code: "unsupported_site",
        error_host: "linkedin.com",
      }),
    );
    const url = "https://www.linkedin.com/post";
    const response = await callAction(url);
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("pending_error=unsupported_site");
    expect(location).toContain(`url=${encodeURIComponent(url)}`);
    expect(location).toContain("host=linkedin.com");
  });

  it("server 500 upstream_error redirects with pending_error and url but no host", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("upstream_error", 500, {
        error_code: "upstream_error",
        message: "boom",
      }),
    );
    const url = "https://example.com/broken";
    const response = await callAction(url);
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("pending_error=upstream_error");
    expect(location).toContain(`url=${encodeURIComponent(url)}`);
    expect(location).not.toContain("host=");
  });

  it("server 400 invalid_url redirects back home (matches client-side behavior)", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("invalid_url", 400, {
        error_code: "invalid_url",
        message: "url rejected",
      }),
    );
    const response = await callAction("https://example.com/p");
    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
  });

  it("transport failure (503 upstream_error from normalizeTransportError) redirects to /analyze?pending_error=upstream_error&url=…", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError(
        "vibecheck /api/analyze transport failure: network broken",
        503,
        { error_code: "upstream_error", message: "network broken" },
      ),
    );
    const url = "https://example.com/broken-transport";
    const response = await callAction(url);
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("/analyze?");
    expect(location).toContain("pending_error=upstream_error");
    expect(location).toContain(`url=${encodeURIComponent(url)}`);
    expect(location).not.toContain("network broken");
  });

  it("URL with embedded ?query and #fragment encodes safely into the redirect", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-q",
      status: "pending",
      cached: false,
    });
    const url = "https://example.com/p?a=1&b=two#frag";
    const response = await callAction(url);
    expect(response.headers.get("Location")).toBe("/analyze?job=job-q");
  });

  it("URL containing CRLF-like control characters yields a Location with no raw newline (header-injection safe)", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-crlf",
      status: "pending",
      cached: false,
    });
    const response = await callAction(
      "https://example.com/p\r\nLocation: https://attacker.example/",
    );
    const location = response.headers.get("Location") ?? "";
    expect(location).toBe("/analyze?job=job-crlf");
    expect(location).not.toContain("\n");
    expect(location).not.toContain("\r");
  });

  it("upstream_error with hostile message in URL: redirect Location encodes the URL exactly and contains no raw newline", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("upstream_error", 500, {
        error_code: "upstream_error",
        message: "ignored",
      }),
    );
    const url = "https://example.com/p?x=hello%20world";
    const response = await callAction(url);
    const location = response.headers.get("Location") ?? "";
    expect(location).toBe(
      `/analyze?pending_error=upstream_error&url=${encodeURIComponent(url)}`,
    );
    expect(location).not.toContain("\n");
    expect(location).not.toContain("\r");
  });

  it("clamps unknown backend error_code to upstream_error in pending_error redirect", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("internal_debug_slug", 500, {
        error_code: "internal_debug_slug" as never,
        message: "leaked debug",
      }),
    );
    const url = "https://example.com/p";
    const response = await callAction(url);
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("pending_error=upstream_error");
    expect(location).not.toContain("internal_debug_slug");
    expect(location).not.toContain("leaked debug");
  });

  it("clamps known but unrelated error_code (rate_limited) into pending_error verbatim", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("rate_limited", 429, {
        error_code: "rate_limited",
        message: "slow down",
      }),
    );
    const url = "https://example.com/p";
    const response = await callAction(url);
    const location = response.headers.get("Location") ?? "";
    expect(location).toContain("pending_error=rate_limited");
    expect(location).toContain(`url=${encodeURIComponent(url)}`);
  });
});

describe("resolveAnalyzeRedirect web-tier rate limiter (TASK-1483.09)", () => {
  const headersWithXff = (clientIp: string) =>
    new Headers({ "x-forwarded-for": `${clientIp}, 10.0.0.1` });

  let currentRequest: Request | null = null;

  async function callWithRequest(
    url: string,
    request: Request,
  ): Promise<Response> {
    currentRequest = request;
    const { resolveAnalyzeRedirect } = await import("./analyze.data");
    const fd = new FormData();
    fd.set("url", url);
    try {
      await resolveAnalyzeRedirect(fd);
      throw new Error("resolveAnalyzeRedirect did not redirect");
    } catch (thrown) {
      if (thrown instanceof Response) return thrown;
      throw thrown;
    }
  }

  beforeEach(async () => {
    analyzeUrlMock.mockReset();
    retrySectionMock.mockReset();
    clientGetMock.mockReset();
    currentRequest = null;
    vi.resetModules();
    vi.doMock("solid-js/web", async () => {
      const actual = await vi.importActual<typeof import("solid-js/web")>(
        "solid-js/web",
      );
      return {
        ...actual,
        getRequestEvent: () =>
          currentRequest
            ? { request: currentRequest, response: new Response() }
            : undefined,
      };
    });
    process.env.NODE_ENV = "production";
    process.env.VIBECHECK_RATE_LIMIT_DISABLED = "0";
    process.env.VIBECHECK_RATE_LIMIT_PER_HOUR = "10";
    const { _resetRateLimitForTesting } = await import(
      "~/lib/rate-limit.server"
    );
    _resetRateLimitForTesting();
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-ok",
      status: "pending",
      cached: false,
    });
  });

  it("eleventh submission from the same client IP redirects to /analyze?pending_error=rate_limited", async () => {
    const url = "https://example.com/p";
    const headers = headersWithXff("203.0.113.10");
    for (let i = 0; i < 10; i++) {
      const r = await callWithRequest(
        url,
        new Request("https://vibecheck.opennotes.ai/", {
          method: "POST",
          headers,
        }),
      );
      const loc = r.headers.get("Location") ?? "";
      expect(loc, `request ${i + 1}/11 should reach analyze`).toContain(
        "/analyze?job=",
      );
    }
    const eleventh = await callWithRequest(
      url,
      new Request("https://vibecheck.opennotes.ai/", {
        method: "POST",
        headers,
      }),
    );
    const loc = eleventh.headers.get("Location") ?? "";
    expect(loc).toContain("pending_error=rate_limited");
    expect(loc).toContain(`url=${encodeURIComponent(url)}`);
  });

  it("twelfth submission from a different client IP is unaffected by the first IP's exhausted bucket", async () => {
    const url = "https://example.com/p";
    const headersA = headersWithXff("203.0.113.10");
    const headersB = headersWithXff("198.51.100.20");
    for (let i = 0; i < 10; i++) {
      await callWithRequest(
        url,
        new Request("https://vibecheck.opennotes.ai/", {
          method: "POST",
          headers: headersA,
        }),
      );
    }
    const denied = await callWithRequest(
      url,
      new Request("https://vibecheck.opennotes.ai/", {
        method: "POST",
        headers: headersA,
      }),
    );
    expect(denied.headers.get("Location") ?? "").toContain(
      "pending_error=rate_limited",
    );
    const allowed = await callWithRequest(
      url,
      new Request("https://vibecheck.opennotes.ai/", {
        method: "POST",
        headers: headersB,
      }),
    );
    expect(allowed.headers.get("Location") ?? "").toContain("/analyze?job=");
  });

  afterEach(() => {
    delete process.env.VIBECHECK_RATE_LIMIT_PER_HOUR;
    delete process.env.VIBECHECK_RATE_LIMIT_DISABLED;
  });
});

describe("getFrameCompat", () => {
  beforeEach(() => {
    analyzeUrlMock.mockReset();
    retrySectionMock.mockReset();
    clientGetMock.mockReset();
    vi.resetModules();
  });

  it("returns archivedPreviewUrl only when the backend reports has_archive=true", async () => {
    clientGetMock.mockImplementation(async (path: string) => {
      if (path === "/api/frame-compat") {
        return {
          data: {
            can_iframe: false,
            blocking_header: "content-security-policy: frame-ancestors 'none'",
            csp_frame_ancestors: "frame-ancestors 'none'",
            has_archive: true,
          },
          error: null,
        };
      }
      if (path === "/api/screenshot") {
        return {
          data: { screenshot_url: "https://cdn.example.com/shot.png" },
          error: null,
        };
      }
      throw new Error(`unexpected path ${path}`);
    });

    const { getFrameCompat } = await import("./analyze.data");
    const result = await getFrameCompat("https://news.example.com/a?x=1");

    expect(result).toEqual({
      ok: true,
      frameCompat: {
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "frame-ancestors 'none'",
        screenshotUrl: "https://cdn.example.com/shot.png",
        archivedPreviewUrl:
          "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fa%3Fx%3D1",
      },
    });
  });

  it("returns null archivedPreviewUrl when has_archive=false", async () => {
    clientGetMock.mockImplementation(async (path: string) => {
      if (path === "/api/frame-compat") {
        return {
          data: {
            can_iframe: false,
            blocking_header: "x-frame-options: DENY",
            csp_frame_ancestors: null,
            has_archive: false,
          },
          error: null,
        };
      }
      if (path === "/api/screenshot") {
        return {
          data: { screenshot_url: "https://cdn.example.com/shot.png" },
          error: null,
        };
      }
      throw new Error(`unexpected path ${path}`);
    });

    const { getFrameCompat } = await import("./analyze.data");
    const result = await getFrameCompat("https://news.example.com/no-archive");

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.frameCompat.archivedPreviewUrl).toBeNull();
    }
  });

  it("does not expose an archive URL for invalid target URLs", async () => {
    const { getFrameCompat } = await import("./analyze.data");
    const result = await getFrameCompat("javascript:alert(1)");

    expect(result).toEqual({ ok: false, message: "invalid url" });
    expect(clientGetMock).not.toHaveBeenCalled();
  });
});

describe("getArchiveProbe and getScreenshot split queries", () => {
  beforeEach(() => {
    analyzeUrlMock.mockReset();
    retrySectionMock.mockReset();
    clientGetMock.mockReset();
    vi.resetModules();
  });

  it("getArchiveProbe calls only /api/frame-compat and returns the tri-state archive payload", async () => {
    clientGetMock.mockImplementation(async (path: string) => {
      if (path === "/api/frame-compat") {
        return {
          data: {
            can_iframe: false,
            blocking_header: "x-frame-options: DENY",
            csp_frame_ancestors: null,
            has_archive: true,
          },
          error: null,
        };
      }
      throw new Error(`unexpected path ${path}`);
    });

    const { getArchiveProbe } = await import("./analyze.data");
    const result = await getArchiveProbe("https://news.example.com/a?x=1");

    expect(result).toEqual({
      ok: true,
      has_archive: true,
      archived_preview_url:
        "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fa%3Fx%3D1",
      can_iframe: false,
      blocking_header: "x-frame-options: DENY",
      csp_frame_ancestors: null,
    });
    expect(clientGetMock).toHaveBeenCalledTimes(1);
    expect(clientGetMock).toHaveBeenCalledWith("/api/frame-compat", {
      params: { query: { url: "https://news.example.com/a?x=1" } },
    });
  });

  it("getArchiveProbe distinguishes invalid URLs from transient frame-compat failures", async () => {
    const { getArchiveProbe } = await import("./analyze.data");

    expect(await getArchiveProbe("javascript:alert(1)")).toEqual({
      ok: false,
      kind: "invalid_url",
    });
    expect(clientGetMock).not.toHaveBeenCalled();

    clientGetMock.mockResolvedValueOnce({ data: null, error: "boom" });
    expect(await getArchiveProbe("https://news.example.com/a")).toEqual({
      ok: false,
      kind: "transient_error",
    });
  });

  it("getArchiveProbe treats malformed frame-compat payloads as transient errors", async () => {
    clientGetMock.mockResolvedValueOnce({
      data: {
        can_iframe: "false",
        blocking_header: ["x-frame-options: DENY"],
        csp_frame_ancestors: null,
        has_archive: true,
      },
      error: null,
    });

    const { getArchiveProbe } = await import("./analyze.data");

    expect(await getArchiveProbe("https://news.example.com/a")).toEqual({
      ok: false,
      kind: "transient_error",
    });
  });

  it("getArchiveProbe treats malformed has_archive values as transient errors", async () => {
    clientGetMock.mockResolvedValueOnce({
      data: {
        can_iframe: false,
        blocking_header: "x-frame-options: DENY",
        csp_frame_ancestors: null,
        has_archive: "false",
      },
      error: null,
    });

    const { getArchiveProbe } = await import("./analyze.data");

    expect(await getArchiveProbe("https://news.example.com/a")).toEqual({
      ok: false,
      kind: "transient_error",
    });
  });

  it("getScreenshot calls only /api/screenshot and returns null for invalid or failed requests", async () => {
    clientGetMock.mockResolvedValueOnce({
      data: { screenshot_url: "https://cdn.example.com/shot.png" },
      error: null,
    });

    const { getScreenshot } = await import("./analyze.data");

    expect(await getScreenshot("https://news.example.com/a")).toBe(
      "https://cdn.example.com/shot.png",
    );
    expect(clientGetMock).toHaveBeenCalledWith("/api/screenshot", {
      params: { query: { url: "https://news.example.com/a" } },
    });

    clientGetMock.mockClear();
    expect(await getScreenshot("not-a-url")).toBeNull();
    expect(clientGetMock).not.toHaveBeenCalled();

    clientGetMock.mockResolvedValueOnce({ data: null, error: "down" });
    expect(await getScreenshot("https://news.example.com/b")).toBeNull();
  });
});
