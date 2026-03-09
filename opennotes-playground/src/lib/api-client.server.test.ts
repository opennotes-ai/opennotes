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

vi.mock("openapi-fetch", () => ({
  default: vi.fn().mockImplementation((opts: any) => {
    const capturedFetch = opts.fetch;
    const capturedHeaders = opts.headers;
    return {
      _opts: opts,
      _capturedFetch: capturedFetch,
      _capturedHeaders: capturedHeaders,
      GET: vi.fn().mockImplementation(async (path: string, _config?: any) => {
        const request = new Request(`${opts.baseUrl}${path}`, {
          headers: capturedHeaders,
        });
        const response = await capturedFetch(request);
        return { data: await response.json(), error: null, response };
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
  process.env = { ...originalEnv };
});

afterEach(() => {
  process.env = originalEnv;
});

describe("getIdentityToken", () => {
  it("returns null in non-production", async () => {
    process.env.NODE_ENV = "development";
    const { getIdentityToken } = await import("./api-client.server");
    const token = await getIdentityToken("https://example.run.app");
    expect(token).toBeNull();
    expect(mockGetIdTokenClient).not.toHaveBeenCalled();
  });

  it("fetches identity token in production", async () => {
    process.env.NODE_ENV = "production";
    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer id-token-123" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const { getIdentityToken } = await import("./api-client.server");
    const token = await getIdentityToken("https://example.run.app");
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

    const { getIdentityToken } = await import("./api-client.server");
    const token = await getIdentityToken("https://example.run.app");
    expect(token).toBe("Bearer retry-token");
    expect(mockGetIdTokenClient).toHaveBeenCalledTimes(2);
  });

  it("throws after 3 failed attempts", async () => {
    process.env.NODE_ENV = "production";
    mockGetIdTokenClient.mockRejectedValue(new Error("persistent failure"));

    const { getIdentityToken } = await import("./api-client.server");
    await expect(
      getIdentityToken("https://example.run.app"),
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

    const { getIdentityToken } = await import("./api-client.server");
    await getIdentityToken("https://example.run.app");
    await getIdentityToken("https://example.run.app");
    await getIdentityToken("https://other.run.app");

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

    const { getIdentityToken } = await import("./api-client.server");
    await getIdentityToken("https://example.run.app");
    await getIdentityToken("https://example.run.app");

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

    const { getIdentityToken } = await import("./api-client.server");
    await getIdentityToken("https://a.run.app");
    await getIdentityToken("https://b.run.app");

    expect(mockGetIdTokenClient).toHaveBeenCalledTimes(2);
    expect(mockGetIdTokenClient).toHaveBeenCalledWith("https://a.run.app");
    expect(mockGetIdTokenClient).toHaveBeenCalledWith("https://b.run.app");
  });

  it("times out after 5 seconds", async () => {
    vi.useFakeTimers();
    process.env.NODE_ENV = "production";
    mockGetIdTokenClient.mockImplementation(
      () => new Promise(() => {}),
    );

    const { getIdentityToken } = await import("./api-client.server");
    const promise = getIdentityToken("https://example.run.app");
    promise.catch(() => {});

    await vi.advanceTimersByTimeAsync(5000);

    await expect(promise).rejects.toThrow(/timed out/i);
    vi.useRealTimers();
  });
});

describe("getClient fetch interceptor", () => {
  it("does not add Authorization header in development", async () => {
    process.env.NODE_ENV = "development";
    process.env.OPENNOTES_SERVER_URL = "http://localhost:8000";
    process.env.OPENNOTES_API_KEY = "test-key";

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: [] }), { status: 200 }),
    );

    const { listSimulations } = await import("./api-client.server");
    await listSimulations();

    const calledRequest = fetchSpy.mock.calls[0][0] as Request;
    expect(calledRequest.headers.get("Authorization")).toBeNull();
    expect(calledRequest.headers.get("X-API-Key")).toBe("test-key");
    fetchSpy.mockRestore();
  });

  it("adds Authorization header in production", async () => {
    process.env.NODE_ENV = "production";
    process.env.OPENNOTES_SERVER_URL = "https://server.run.app";
    process.env.OPENNOTES_API_KEY = "prod-key";

    mockGetRequestHeaders.mockResolvedValue(
      mockHeaders({ Authorization: "Bearer prod-id-token" }),
    );
    mockGetIdTokenClient.mockResolvedValue({
      getRequestHeaders: mockGetRequestHeaders,
    });

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: [] }), { status: 200 }),
    );

    const { listSimulations } = await import("./api-client.server");
    await listSimulations();

    const calledRequest = fetchSpy.mock.calls[0][0] as Request;
    expect(calledRequest.headers.get("Authorization")).toBe(
      "Bearer prod-id-token",
    );
    expect(calledRequest.headers.get("X-API-Key")).toBe("prod-key");
    fetchSpy.mockRestore();
  });
});
