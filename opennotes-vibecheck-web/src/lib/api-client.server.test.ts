import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const mockGoogleAuthConstructor = vi.fn();
const mockGetIdTokenClient = vi.fn();
const mockGetRequestHeaders = vi.fn();

vi.mock("google-auth-library", () => ({
  GoogleAuth: vi.fn().mockImplementation(function () {
    mockGoogleAuthConstructor();
    return { getIdTokenClient: mockGetIdTokenClient };
  }),
}));

let capturedFetchInterceptor: ((req: Request) => Promise<Response>) | null =
  null;

vi.mock("openapi-fetch", () => ({
  default: vi.fn().mockImplementation((opts: any) => {
    const capturedFetch = opts.fetch;
    capturedFetchInterceptor = capturedFetch;
    return {
      _opts: opts,
      _capturedFetch: capturedFetch,
      POST: vi.fn().mockImplementation(async (path: string, config?: any) => {
        const request = new Request(`${opts.baseUrl}${path}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config?.body ?? {}),
        });
        const response = await capturedFetch(request);
        const bodyText = await response.text();
        const parsed = bodyText ? JSON.parse(bodyText) : null;
        if (!response.ok) {
          return { data: null, error: parsed ?? {}, response };
        }
        return { data: parsed, error: null, response };
      }),
    };
  }),
}));

function mockHeaders(init?: Record<string, string>): Headers {
  return new Headers(init);
}

const originalEnv = { ...process.env };

beforeEach(() => {
  vi.resetModules();
  mockGoogleAuthConstructor.mockReset();
  mockGetIdTokenClient.mockReset();
  mockGetRequestHeaders.mockReset();
  capturedFetchInterceptor = null;
  process.env = { ...originalEnv };
  delete process.env.VIBECHECK_SERVER_URL;
  delete process.env.NODE_ENV;
});

afterEach(() => {
  process.env = originalEnv;
});

describe("resolveBaseUrl (via getClient)", () => {
  it("uses VIBECHECK_SERVER_URL when set", async () => {
    process.env.NODE_ENV = "development";
    process.env.VIBECHECK_SERVER_URL = "https://custom.run.app";
    const { getClient } = await import("./api-client.server");
    const client = getClient() as unknown as { _opts: { baseUrl: string } };
    expect(client._opts.baseUrl).toBe("https://custom.run.app");
  });

  it("defaults to http://localhost:8000 in development when unset", async () => {
    process.env.NODE_ENV = "development";
    const { getClient } = await import("./api-client.server");
    const client = getClient() as unknown as { _opts: { baseUrl: string } };
    expect(client._opts.baseUrl).toBe("http://localhost:8000");
  });

  it("throws in production when VIBECHECK_SERVER_URL is unset", async () => {
    process.env.NODE_ENV = "production";
    const { getClient } = await import("./api-client.server");
    expect(() => getClient()).toThrow(/VIBECHECK_SERVER_URL/);
  });

  it("prefers VIBECHECK_SERVER_URL in production", async () => {
    process.env.NODE_ENV = "production";
    process.env.VIBECHECK_SERVER_URL = "https://prod.run.app";
    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer prod-token" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });
    const { getClient } = await import("./api-client.server");
    const client = getClient() as unknown as { _opts: { baseUrl: string } };
    expect(client._opts.baseUrl).toBe("https://prod.run.app");
  });
});

describe("getAuthorizationHeader", () => {
  it("returns null in non-production", async () => {
    process.env.NODE_ENV = "development";
    const { getAuthorizationHeader } = await import("./api-client.server");
    const token = await getAuthorizationHeader("https://example.run.app");
    expect(token).toBeNull();
    expect(mockGetIdTokenClient).not.toHaveBeenCalled();
  });

  it("fetches identity token in production with server URL as audience", async () => {
    process.env.NODE_ENV = "production";
    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer id-token-123" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const { getAuthorizationHeader } = await import("./api-client.server");
    const token = await getAuthorizationHeader("https://example.run.app");
    expect(token).toBe("Bearer id-token-123");
    expect(mockGetIdTokenClient).toHaveBeenCalledWith(
      "https://example.run.app",
    );
  });

  it("retries on transient failure then succeeds", async () => {
    process.env.NODE_ENV = "production";
    mockGetIdTokenClient
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce({
        getRequestHeaders: mockGetRequestHeaders.mockResolvedValue(
          mockHeaders({ Authorization: "Bearer retry-token" }),
        ),
      });

    const { getAuthorizationHeader } = await import("./api-client.server");
    const token = await getAuthorizationHeader("https://example.run.app");
    expect(token).toBe("Bearer retry-token");
    expect(mockGetIdTokenClient).toHaveBeenCalledTimes(2);
  });

  it("throws after 3 failed attempts", async () => {
    process.env.NODE_ENV = "production";
    mockGetIdTokenClient.mockRejectedValue(new Error("persistent failure"));

    const { getAuthorizationHeader } = await import("./api-client.server");
    await expect(
      getAuthorizationHeader("https://example.run.app"),
    ).rejects.toThrow("persistent failure");
    expect(mockGetIdTokenClient).toHaveBeenCalledTimes(3);
  });

  it("caches GoogleAuth as a singleton across calls", async () => {
    process.env.NODE_ENV = "production";
    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer token-1" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const { getAuthorizationHeader } = await import("./api-client.server");
    await getAuthorizationHeader("https://example.run.app");
    await getAuthorizationHeader("https://example.run.app");
    await getAuthorizationHeader("https://other.run.app");

    expect(mockGoogleAuthConstructor).toHaveBeenCalledTimes(1);
  });

  it("caches IdTokenClient per audience", async () => {
    process.env.NODE_ENV = "production";
    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer cached-token" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const { getAuthorizationHeader } = await import("./api-client.server");
    await getAuthorizationHeader("https://example.run.app");
    await getAuthorizationHeader("https://example.run.app");

    expect(mockGetIdTokenClient).toHaveBeenCalledTimes(1);
  });

  it("creates separate IdTokenClient for different audiences", async () => {
    process.env.NODE_ENV = "production";
    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer token" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const { getAuthorizationHeader } = await import("./api-client.server");
    await getAuthorizationHeader("https://a.run.app");
    await getAuthorizationHeader("https://b.run.app");

    expect(mockGetIdTokenClient).toHaveBeenCalledTimes(2);
    expect(mockGetIdTokenClient).toHaveBeenCalledWith("https://a.run.app");
    expect(mockGetIdTokenClient).toHaveBeenCalledWith("https://b.run.app");
  });

  it("times out after 5 seconds", async () => {
    vi.useFakeTimers();
    process.env.NODE_ENV = "production";
    mockGetIdTokenClient.mockImplementation(() => new Promise(() => {}));

    const { getAuthorizationHeader } = await import("./api-client.server");
    const promise = getAuthorizationHeader("https://example.run.app");
    promise.catch(() => {});

    await vi.advanceTimersByTimeAsync(5000);

    await expect(promise).rejects.toThrow(/timed out/i);
    vi.useRealTimers();
  });
});

describe("analyzeUrl", () => {
  const samplePayload = {
    job_id: "00000000-0000-0000-0000-000000000001",
    status: "pending",
    cached: false,
  };

  const freshPayloadResponse = (status = 202) =>
    new Response(JSON.stringify(samplePayload), { status });

  it("does not add Authorization header in development", async () => {
    process.env.NODE_ENV = "development";
    process.env.VIBECHECK_SERVER_URL = "http://localhost:8000";

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => freshPayloadResponse());

    const { analyzeUrl } = await import("./api-client.server");
    const result = await analyzeUrl("https://news.example.com/a");

    const calledRequest = fetchSpy.mock.calls[0][0] as Request;
    expect(calledRequest.headers.get("Authorization")).toBeNull();
    expect(result).toEqual(samplePayload);
    expect(mockGetIdTokenClient).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("adds Authorization header in production", async () => {
    process.env.NODE_ENV = "production";
    process.env.VIBECHECK_SERVER_URL = "https://server.run.app";

    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer prod-id-token" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => freshPayloadResponse());

    const { analyzeUrl } = await import("./api-client.server");
    await analyzeUrl("https://news.example.com/a");

    const calledRequest = fetchSpy.mock.calls[0][0] as Request;
    expect(calledRequest.headers.get("Authorization")).toBe(
      "Bearer prod-id-token",
    );
    expect(mockGetIdTokenClient).toHaveBeenCalledWith("https://server.run.app");
    fetchSpy.mockRestore();
  });

  it("throws VibecheckApiError with statusCode when backend returns non-2xx", async () => {
    process.env.NODE_ENV = "development";
    process.env.VIBECHECK_SERVER_URL = "http://localhost:8000";

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              error_code: "invalid_url",
              message: "bad url",
            }),
            { status: 400 },
          ),
      );

    const { analyzeUrl, VibecheckApiError } = await import(
      "./api-client.server"
    );

    let caught: unknown = null;
    try {
      await analyzeUrl("not a url");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(VibecheckApiError);
    const apiErr = caught as InstanceType<typeof VibecheckApiError>;
    expect(apiErr.statusCode).toBe(400);
    expect(apiErr.errorBody).toEqual({
      error_code: "invalid_url",
      message: "bad url",
    });

    fetchSpy.mockRestore();
  });

  it("parses error_host from a 422 unsupported_site response", async () => {
    process.env.NODE_ENV = "development";
    process.env.VIBECHECK_SERVER_URL = "http://localhost:8000";

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              error_code: "unsupported_site",
              message: "blocked host",
              error_host: "linkedin.com",
            }),
            { status: 422 },
          ),
      );

    const { analyzeUrl, VibecheckApiError } = await import(
      "./api-client.server"
    );

    let caught: unknown = null;
    try {
      await analyzeUrl("https://www.linkedin.com/post");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(VibecheckApiError);
    const apiErr = caught as InstanceType<typeof VibecheckApiError>;
    expect(apiErr.errorBody?.error_host).toBe("linkedin.com");
    expect(apiErr.errorBody?.error_code).toBe("unsupported_site");

    fetchSpy.mockRestore();
  });

  it("wraps identity token failures in VibecheckApiError(503)", async () => {
    process.env.NODE_ENV = "production";
    process.env.VIBECHECK_SERVER_URL = "https://server.run.app";

    mockGetIdTokenClient.mockRejectedValue(new Error("auth failure"));

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => freshPayloadResponse());

    const { analyzeUrl, VibecheckApiError } = await import(
      "./api-client.server"
    );

    let caught: unknown = null;
    try {
      await analyzeUrl("https://news.example.com/a");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(VibecheckApiError);
    expect((caught as InstanceType<typeof VibecheckApiError>).statusCode).toBe(
      503,
    );
    expect((caught as Error).message).toMatch(/Failed to fetch identity token/);
    fetchSpy.mockRestore();
  });

  it("retries once on network error then succeeds", async () => {
    process.env.NODE_ENV = "development";
    process.env.VIBECHECK_SERVER_URL = "http://localhost:8000";

    let callCount = 0;
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => {
        callCount++;
        if (callCount === 1) throw new TypeError("network broken");
        return freshPayloadResponse();
      });

    const { analyzeUrl } = await import("./api-client.server");
    const result = await analyzeUrl("https://news.example.com/a");
    expect(result).toEqual(samplePayload);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    fetchSpy.mockRestore();
  });

  it("normalizes transport failures to VibecheckApiError(503, upstream_error)", async () => {
    process.env.NODE_ENV = "development";
    process.env.VIBECHECK_SERVER_URL = "http://localhost:8000";

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => {
        throw new TypeError("network broken");
      });

    const { analyzeUrl, VibecheckApiError } = await import(
      "./api-client.server"
    );
    let caught: unknown = null;
    try {
      await analyzeUrl("https://news.example.com/a");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(VibecheckApiError);
    const apiErr = caught as InstanceType<typeof VibecheckApiError>;
    expect(apiErr.statusCode).toBe(503);
    expect(apiErr.errorBody?.error_code).toBe("upstream_error");
    expect(apiErr.errorBody?.message).toMatch(/network broken/);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    fetchSpy.mockRestore();
  });
});
