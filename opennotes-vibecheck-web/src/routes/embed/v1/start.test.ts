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

import type { APIEvent } from "@solidjs/start/server";

function makeEvent(request: Request): APIEvent {
  return {
    request,
    response: new Response(),
    locals: {},
    params: {},
    nativeEvent: {} as never,
  } as APIEvent;
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
    const loc = response.headers.get("Location") ?? "";
    const params = new URLSearchParams(loc.split("?")[1]);
    expect(params.get("job")).toBe("job-abc");
    expect(params.get("url")).toBe("https://example.com/p");
    expect(response.headers.get("Cache-Control")).toBe("no-store, private");
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

  it("formData() parse failure (malformed multipart) falls back to /?error=invalid_url with relative Location", async () => {
    const req = new Request("https://vibecheck.opennotes.ai/embed/v1/start", {
      method: "POST",
      headers: { "content-type": "multipart/form-data; boundary=---x" },
      body: "this is not multipart",
    });
    const { POST } = await import("./start");
    const response = await POST(makeEvent(req));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/?error=invalid_url");
    expect(response.headers.get("Cache-Control")).toBe("no-store, private");
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

  it("non-redirect Response thrown by inner handler is rewritten to 500 (does not leak inner body)", async () => {
    analyzeUrlMock.mockImplementation(async () => {
      throw new Response("inner-body", { status: 200 });
    });
    const { POST } = await import("./start");
    const response = await POST(makeEvent(fdRequest("POST", "https://example.com/p")));
    expect(response.status).toBe(500);
    expect(await response.text()).toBe("");
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
    const loc = response.headers.get("Location") ?? "";
    const params = new URLSearchParams(loc.split("?")[1]);
    expect(params.get("job")).toBe("job-multipart");
    expect(params.get("url")).toBe("https://example.com/p");
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
    const loc = response.headers.get("Location") ?? "";
    const params = new URLSearchParams(loc.split("?")[1]);
    expect(params.get("job")).toBe("job-urlencoded");
    expect(params.get("url")).toBe("https://example.com/p");
  });

  it("POST invokes analyzeUrl exactly once per request (downstream dedup is enforced by the backend single-flight, not this layer)", async () => {
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

describe("non-POST methods on /embed/v1/start", () => {
  it.each(["GET", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] as const)(
    "%s returns 405 with Allow: POST and Cache-Control: no-store",
    async (method) => {
      const mod = await import("./start");
      const handler = mod[method as keyof typeof mod] as () => Promise<Response>;
      const response = await handler();
      expect(response.status).toBe(405);
      expect(response.headers.get("Allow")).toBe("POST");
      expect(response.headers.get("Cache-Control")).toBe("no-store, private");
    },
  );
});
