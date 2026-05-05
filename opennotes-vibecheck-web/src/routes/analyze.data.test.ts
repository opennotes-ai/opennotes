import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { MAX_PDF_BYTES } from "~/lib/pdf-constraints";

const {
  analyzeUrlMock,
  pollJobMock,
  retrySectionMock,
  clientGetMock,
  requestPdfUploadUrlMock,
  requestPdfAnalysisMock,
} = vi.hoisted(() => ({
  analyzeUrlMock: vi.fn(),
  pollJobMock: vi.fn(),
  retrySectionMock: vi.fn(),
  clientGetMock: vi.fn(),
  requestPdfUploadUrlMock: vi.fn(),
  requestPdfAnalysisMock: vi.fn(),
}));

vi.mock("~/lib/api-client.server", async () => {
  const actual = await vi.importActual<
    typeof import("~/lib/api-client.server")
  >("~/lib/api-client.server");
  return {
    ...actual,
    analyzeUrl: analyzeUrlMock,
    pollJob: pollJobMock,
    retrySection: retrySectionMock,
    requestPdfUploadUrl: requestPdfUploadUrlMock,
    requestPdfAnalysis: requestPdfAnalysisMock,
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

async function callPdfAction(file?: File): Promise<Response> {
  const { resolveAnalyzePdfRedirect } = await import("./analyze.data");
  const fd = new FormData();
  if (file) {
    fd.set("pdf", file);
  }
  try {
    await resolveAnalyzePdfRedirect(fd);
    throw new Error("resolveAnalyzePdfRedirect did not redirect");
  } catch (thrown) {
    if (thrown instanceof Response) return thrown;
    throw thrown;
  }
}

async function callPdfActionAsFile(name = "notes.pdf"): Promise<Response> {
  const file = new File([new Uint8Array(16)], name, { type: "application/pdf" });
  return callPdfAction(file);
}

describe("analyzeAction", () => {
  beforeEach(() => {
    analyzeUrlMock.mockReset();
    pollJobMock.mockReset();
    retrySectionMock.mockReset();
    clientGetMock.mockReset();
    requestPdfUploadUrlMock.mockReset();
    requestPdfAnalysisMock.mockReset();
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
    const location = response.headers.get("Location") ?? "";
    const params = new URLSearchParams(location.split("?")[1]);
    expect(params.get("job")).toBe("job-q");
    expect(params.get("url")).toBe(url);
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
    expect(location).toContain("job=job-crlf");
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

describe("analyzePdfAction", () => {
  const createPdf = (size: number, name = "policy.pdf") =>
    new File([new Uint8Array(size)], name, { type: "application/pdf" });

  beforeEach(() => {
    requestPdfUploadUrlMock.mockReset();
    requestPdfAnalysisMock.mockReset();
    vi.resetModules();
  });

  it("calls requestPdfUploadUrl then requestPdfAnalysis and redirects to /analyze?job=<id>", async () => {
    requestPdfUploadUrlMock.mockResolvedValue({
      gcs_key: "gcs-key",
      upload_url: "https://storage.example.com/upload",
    });
    requestPdfAnalysisMock.mockResolvedValue({
      job_id: "pdf-job-1",
      status: "pending",
      cached: false,
    });

    const file = createPdf(12);
    const response = await callPdfAction(file);
    const location = response.headers.get("Location") ?? "";
    const params = new URLSearchParams(location.split("?")[1]);

    expect(params.get("job")).toBe("pdf-job-1");
    expect(params.get("filename")).toBe("policy.pdf");
    expect(requestPdfUploadUrlMock).toHaveBeenCalledTimes(1);
    expect(requestPdfAnalysisMock).toHaveBeenCalledWith("gcs-key", "policy.pdf");
  });

  it("redirects home without backend calls when no PDF file is present", async () => {
    const response = await callPdfAction();

    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
    expect(requestPdfUploadUrlMock).not.toHaveBeenCalled();
    expect(requestPdfAnalysisMock).not.toHaveBeenCalled();
  });

  it("redirects home without backend calls for non-PDF files", async () => {
    const response = await callPdfAction(
      new File(["hello"], "notes.txt", { type: "text/plain" }),
    );

    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
    expect(requestPdfUploadUrlMock).not.toHaveBeenCalled();
    expect(requestPdfAnalysisMock).not.toHaveBeenCalled();
  });

  it("redirects home without backend calls for oversized PDFs", async () => {
    const response = await callPdfAction(createPdf(MAX_PDF_BYTES + 1));

    expect(response.headers.get("Location")).toBe("/?error=pdf_too_large");
    expect(requestPdfUploadUrlMock).not.toHaveBeenCalled();
    expect(requestPdfAnalysisMock).not.toHaveBeenCalled();
  });

  it("maps pdf_too_large backend error to home error route", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    requestPdfUploadUrlMock.mockResolvedValue({
      gcs_key: "gcs-key",
      upload_url: "https://storage.example.com/upload",
    });
    requestPdfAnalysisMock.mockRejectedValue(
      new VibecheckApiError("too_large", 413, {
        error_code: "pdf_too_large" as never,
      }),
    );

    const response = await callPdfAction(createPdf(16));
    const location = response.headers.get("Location") ?? "";
    expect(location).toBe("/?error=pdf_too_large");
  });

  it("maps pdf_extraction_failed backend error to home error page", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    requestPdfUploadUrlMock.mockResolvedValue({
      gcs_key: "gcs-key",
      upload_url: "https://storage.example.com/upload",
    });
    requestPdfAnalysisMock.mockRejectedValue(
      new VibecheckApiError("bad pdf", 400, {
        error_code: "pdf_extraction_failed",
      }),
    );

    const response = await callPdfAction(createPdf(16, "paper.pdf"));
    const location = response.headers.get("Location") ?? "";
    expect(location).toBe("/?error=pdf_extraction_failed");
    expect(location).not.toContain("pending_error=");
    expect(location).not.toContain("paper.pdf");
  });

  it("rate limits PDF uploads when over threshold", async () => {
    let currentRequest: Request | null = null;
    const origNodeEnv = process.env.NODE_ENV;
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
    const { _resetRateLimitForTesting } = await import(
      "~/lib/rate-limit.server"
    );
    try {
      process.env.NODE_ENV = "production";
      process.env.VIBECHECK_RATE_LIMIT_DISABLED = "0";
      process.env.VIBECHECK_RATE_LIMIT_PER_HOUR = "2";
      _resetRateLimitForTesting();
      requestPdfUploadUrlMock.mockResolvedValue({
        gcs_key: "gcs-key",
        upload_url: "https://storage.example.com/upload",
      });
      requestPdfAnalysisMock.mockResolvedValue({
        job_id: "pdf-rl-job",
        status: "pending",
        cached: false,
      });

      const file = new File([new Uint8Array(16)], "doc.pdf", {
        type: "application/pdf",
      });
      const headers = new Headers({ "x-forwarded-for": "203.0.113.42, 10.0.0.1" });
      const makeRequest = () =>
        new Request("https://vibecheck.opennotes.ai/", {
          method: "POST",
          headers,
        });

      const { resolveAnalyzePdfRedirect } = await import("./analyze.data");

      const call = async () => {
        currentRequest = makeRequest();
        const fd = new FormData();
        fd.set("pdf", file);
        try {
          await resolveAnalyzePdfRedirect(fd);
          throw new Error("did not redirect");
        } catch (thrown) {
          if (thrown instanceof Response) return thrown;
          throw thrown;
        }
      };

      const r1 = await call();
      expect(r1.headers.get("Location")).toContain("/analyze?job=");
      const r2 = await call();
      expect(r2.headers.get("Location")).toContain("/analyze?job=");
      const r3 = await call();
      expect(r3.headers.get("Location")).toContain("pending_error=rate_limited");
    } finally {
      vi.doUnmock("solid-js/web");
      _resetRateLimitForTesting();
      if (origNodeEnv !== undefined) {
        process.env.NODE_ENV = origNodeEnv;
      } else {
        delete process.env.NODE_ENV;
      }
      delete process.env.VIBECHECK_RATE_LIMIT_PER_HOUR;
      delete process.env.VIBECHECK_RATE_LIMIT_DISABLED;
    }
  });
});

describe("resolveAnalyzeRedirect web-tier rate limiter (TASK-1483.09)", () => {
  const headersWithXff = (clientIp: string) =>
    new Headers({ "x-forwarded-for": `${clientIp}, 10.0.0.1` });

  let currentRequest: Request | null = null;
  let origNodeEnv: string | undefined;

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
    pollJobMock.mockReset();
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
    origNodeEnv = process.env.NODE_ENV;
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
    if (origNodeEnv !== undefined) {
      process.env.NODE_ENV = origNodeEnv;
    } else {
      delete process.env.NODE_ENV;
    }
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
    const result = await getFrameCompat(
      "https://news.example.com/a?x=1",
      "11111111-1111-1111-1111-111111111111",
    );

    expect(result).toEqual({
      ok: true,
      frameCompat: {
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "frame-ancestors 'none'",
        screenshotUrl: "https://cdn.example.com/shot.png",
        archivedPreviewUrl:
          "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fa%3Fx%3D1&job_id=11111111-1111-1111-1111-111111111111",
      },
    });
    expect(clientGetMock).toHaveBeenCalledWith("/api/screenshot", {
      params: {
        query: {
          url: "https://news.example.com/a?x=1",
          job_id: "11111111-1111-1111-1111-111111111111",
        },
      },
    });
  });

  it("builds an archivedPreviewUrl without job_id when no job id is supplied", async () => {
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
      if (path === "/api/screenshot") {
        return { data: { screenshot_url: null }, error: null };
      }
      throw new Error(`unexpected path ${path}`);
    });

    const { getFrameCompat } = await import("./analyze.data");
    const result = await getFrameCompat("https://news.example.com/no-job");

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.frameCompat.archivedPreviewUrl).toBe(
        "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fno-job",
      );
    }
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
    const result = await getArchiveProbe(
      "https://news.example.com/a?x=1",
      "11111111-1111-1111-1111-111111111111",
    );

    expect(result).toEqual({
      ok: true,
      has_archive: true,
      archived_preview_url:
        "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fa%3Fx%3D1&job_id=11111111-1111-1111-1111-111111111111",
      can_iframe: false,
      blocking_header: "x-frame-options: DENY",
      csp_frame_ancestors: null,
    });
    expect(clientGetMock).toHaveBeenCalledTimes(1);
    expect(clientGetMock).toHaveBeenCalledWith("/api/frame-compat", {
      params: {
        query: {
          url: "https://news.example.com/a?x=1",
          job_id: "11111111-1111-1111-1111-111111111111",
        },
      },
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

  it("getArchiveProbe accepts responses without has_archive field (rolling deploy compat — TASK-1498.23)", async () => {
    clientGetMock.mockResolvedValueOnce({
      data: {
        can_iframe: true,
        blocking_header: null,
        csp_frame_ancestors: null,
      },
      error: null,
    });

    const { getArchiveProbe } = await import("./analyze.data");

    const result = await getArchiveProbe("https://news.example.com/a");
    expect(result).toEqual({
      ok: true,
      has_archive: false,
      archived_preview_url: null,
      can_iframe: true,
      blocking_header: null,
      csp_frame_ancestors: null,
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

  it("getScreenshot forwards job_id when supplied", async () => {
    clientGetMock.mockResolvedValueOnce({
      data: { screenshot_url: "https://cdn.example.com/job-shot.png" },
      error: null,
    });

    const { getScreenshot } = await import("./analyze.data");

    expect(
      await getScreenshot(
        "https://news.example.com/a",
        "11111111-1111-1111-1111-111111111111",
      ),
    ).toBe("https://cdn.example.com/job-shot.png");
    expect(clientGetMock).toHaveBeenCalledWith("/api/screenshot", {
      params: {
        query: {
          url: "https://news.example.com/a",
          job_id: "11111111-1111-1111-1111-111111111111",
        },
      },
    });
  });

  it("getScreenshot treats typed 404 responses as null without warning", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    clientGetMock.mockResolvedValueOnce({
      data: null,
      error: {
        status: 404,
        detail: "Site not supported",
        reason: "unsupported_site",
      },
    });

    try {
      const { getScreenshot } = await import("./analyze.data");

      expect(await getScreenshot("https://news.example.com/a")).toBeNull();
      expect(warnSpy).not.toHaveBeenCalled();
    } finally {
      warnSpy.mockRestore();
    }
  });

  it("getScreenshot warns for transient screenshot failures", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    clientGetMock.mockResolvedValueOnce({
      data: null,
      error: { status: 502, detail: "Screenshot service failed" },
    });

    try {
      const { getScreenshot } = await import("./analyze.data");

      expect(await getScreenshot("https://news.example.com/a")).toBeNull();
      expect(warnSpy).toHaveBeenCalledTimes(1);
    } finally {
      warnSpy.mockRestore();
    }
  });
});

describe("getJobState query", () => {
  beforeEach(() => {
    pollJobMock.mockReset();
    vi.resetModules();
  });

  it("uses a stable key and returns the same JobState shape as pollJob", async () => {
    const state = {
      job_id: "job-abc",
      status: "done",
      url: "https://news.example.com/a",
      cached: true,
      next_poll_ms: 1500,
    };
    pollJobMock.mockResolvedValueOnce(state);

    const { getJobState } = await import("./analyze.data");

    expect(getJobState.keyFor("job-abc")).toEqual(
      getJobState.keyFor("job-abc"),
    );
    await expect(getJobState("job-abc")).resolves.toEqual(state);
    expect(pollJobMock).toHaveBeenCalledWith("job-abc");
  });
});
