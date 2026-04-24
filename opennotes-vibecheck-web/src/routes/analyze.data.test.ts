import { describe, expect, it, vi, beforeEach } from "vitest";

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
