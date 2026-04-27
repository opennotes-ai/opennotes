import { describe, expect, it, vi, beforeEach } from "vitest";

const { analyzeUrlMock } = vi.hoisted(() => ({ analyzeUrlMock: vi.fn() }));

vi.mock("~/lib/api-client.server", async () => {
  const actual =
    await vi.importActual<typeof import("~/lib/api-client.server")>(
      "~/lib/api-client.server",
    );
  return {
    ...actual,
    analyzeUrl: analyzeUrlMock,
    getClient: () => ({ GET: vi.fn(), POST: vi.fn() }),
  };
});

function makeEvent(request: Request) {
  return { request, response: new Response(), locals: {} } as never;
}

function fdRequest(method: string, url: string | null): Request {
  const fd = new FormData();
  if (url !== null) fd.set("url", url);
  return new Request("https://vibecheck.opennotes.ai/embed/v1/start", {
    method,
    body: fd,
  });
}

describe("POST /embed/v1/start", () => {
  beforeEach(() => {
    analyzeUrlMock.mockReset();
    vi.resetModules();
  });

  it("redirects 303 to /analyze?job=<id> on a successful submit", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-abc",
      status: "pending",
      cached: false,
    });
    const { POST } = await import("./start");
    const response = await POST(makeEvent(fdRequest("POST", "https://example.com/p")));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/analyze?job=job-abc");
  });

  it("appends &c=1 when the response is cached", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-cached",
      status: "done",
      cached: true,
    });
    const { POST } = await import("./start");
    const response = await POST(makeEvent(fdRequest("POST", "https://example.com/p")));
    expect(response.status).toBe(303);
    const loc = response.headers.get("Location") ?? "";
    expect(loc).toContain("job=job-cached");
    expect(loc).toContain("c=1");
  });

  it("invalid url falls back to /?error=invalid_url", async () => {
    const { POST } = await import("./start");
    const response = await POST(makeEvent(fdRequest("POST", "not-a-url")));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
    expect(analyzeUrlMock).not.toHaveBeenCalled();
  });

  it("missing url field falls back to /?error=invalid_url", async () => {
    const { POST } = await import("./start");
    const response = await POST(makeEvent(fdRequest("POST", null)));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
    expect(analyzeUrlMock).not.toHaveBeenCalled();
  });

  it("unsupported_site backend error redirects to /analyze?pending_error=unsupported_site&url=&host=", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("unsupported_site", 422, {
        error_code: "unsupported_site",
        error_host: "linkedin.com",
      }),
    );
    const { POST } = await import("./start");
    const url = "https://www.linkedin.com/x";
    const response = await POST(makeEvent(fdRequest("POST", url)));
    const loc = response.headers.get("Location") ?? "";
    expect(response.status).toBe(303);
    expect(loc).toContain("pending_error=unsupported_site");
    expect(loc).toContain(`url=${encodeURIComponent(url)}`);
    expect(loc).toContain("host=linkedin.com");
  });

  it("upstream_error redirects to /analyze?pending_error=upstream_error&url=…", async () => {
    const { VibecheckApiError } = await import("~/lib/api-client.server");
    analyzeUrlMock.mockRejectedValue(
      new VibecheckApiError("upstream_error", 500, {
        error_code: "upstream_error",
      }),
    );
    const { POST } = await import("./start");
    const url = "https://example.com/broken";
    const response = await POST(makeEvent(fdRequest("POST", url)));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toContain(
      "pending_error=upstream_error",
    );
  });

  it("accepts multipart/form-data submissions", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-multipart",
      status: "pending",
      cached: false,
    });
    const fd = new FormData();
    fd.set("url", "https://example.com/p");
    const req = new Request(
      "https://vibecheck.opennotes.ai/embed/v1/start",
      { method: "POST", body: fd },
    );
    const ct = req.headers.get("content-type") ?? "";
    expect(ct.startsWith("multipart/form-data")).toBe(true);
    const { POST } = await import("./start");
    const response = await POST(makeEvent(req));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/analyze?job=job-multipart");
  });

  it("accepts application/x-www-form-urlencoded submissions", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-urlencoded",
      status: "pending",
      cached: false,
    });
    const body = new URLSearchParams({ url: "https://example.com/p" }).toString();
    const req = new Request(
      "https://vibecheck.opennotes.ai/embed/v1/start",
      {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body,
      },
    );
    const { POST } = await import("./start");
    const response = await POST(makeEvent(req));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/analyze?job=job-urlencoded");
  });

  it("calls analyzeUrl exactly once per POST (exactly-once submission counting)", async () => {
    analyzeUrlMock.mockResolvedValue({
      job_id: "job-once",
      status: "pending",
      cached: false,
    });
    const { POST } = await import("./start");
    await POST(makeEvent(fdRequest("POST", "https://example.com/p")));
    expect(analyzeUrlMock).toHaveBeenCalledTimes(1);
  });
});

describe("GET (and other non-POST methods) /embed/v1/start", () => {
  it("returns 405 with Allow: POST", async () => {
    const { GET } = await import("./start");
    const response = await GET();
    expect(response.status).toBe(405);
    expect(response.headers.get("Allow")).toBe("POST");
  });

  it("PUT returns 405 with Allow: POST", async () => {
    const { PUT } = await import("./start");
    const response = await PUT();
    expect(response.status).toBe(405);
    expect(response.headers.get("Allow")).toBe("POST");
  });

  it("DELETE returns 405 with Allow: POST", async () => {
    const { DELETE } = await import("./start");
    const response = await DELETE();
    expect(response.status).toBe(405);
    expect(response.headers.get("Allow")).toBe("POST");
  });
});
