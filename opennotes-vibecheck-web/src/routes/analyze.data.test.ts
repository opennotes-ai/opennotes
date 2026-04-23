import { describe, expect, it, vi, beforeEach } from "vitest";

const { analyzeUrlMock, retrySectionMock } = vi.hoisted(() => ({
  analyzeUrlMock: vi.fn(),
  retrySectionMock: vi.fn(),
}));

vi.mock("~/lib/api-client.server", async () => {
  const actual = await vi.importActual<
    typeof import("~/lib/api-client.server")
  >("~/lib/api-client.server");
  return {
    ...actual,
    analyzeUrl: analyzeUrlMock,
    retrySection: retrySectionMock,
    getClient: () => ({ GET: vi.fn(), POST: vi.fn() }),
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
});
