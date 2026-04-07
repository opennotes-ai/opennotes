import { describe, expect, it, vi, beforeEach } from "vitest";
import { safeRedirectPath } from "../../lib/safe-redirect";

const mockExchangeCodeForSession = vi.fn();
const mockCreateClient = vi.fn();

vi.mock("~/lib/supabase-server", () => ({
  createClient: (...args: any[]) => mockCreateClient(...args),
}));


describe("safeRedirectPath", () => {
  it("returns / for null", () => {
    expect(safeRedirectPath(null)).toBe("/");
  });

  it("returns / for empty string", () => {
    expect(safeRedirectPath("")).toBe("/");
  });

  it("returns / for protocol-relative URL (//evil.com)", () => {
    expect(safeRedirectPath("//evil.com")).toBe("/");
  });

  it("returns / for backslash URL (\\evil.com)", () => {
    expect(safeRedirectPath("\\evil.com")).toBe("/");
  });

  it("returns / for embedded :// (http://evil.com)", () => {
    expect(safeRedirectPath("http://evil.com")).toBe("/");
  });

  it("returns / for https:// URL", () => {
    expect(safeRedirectPath("https://evil.com")).toBe("/");
  });

  it("allows valid absolute path /dashboard", () => {
    expect(safeRedirectPath("/dashboard")).toBe("/dashboard");
  });

  it("allows root path /", () => {
    expect(safeRedirectPath("/")).toBe("/");
  });

  it("allows nested path /a/b/c", () => {
    expect(safeRedirectPath("/a/b/c")).toBe("/a/b/c");
  });

  it("returns / for path with :// embedded after slash", () => {
    expect(safeRedirectPath("/foo://bar")).toBe("/");
  });

  it("returns / for backslash after leading slash (/\\evil.com)", () => {
    expect(safeRedirectPath("/\\evil.com")).toBe("/");
  });

  it("returns / for backslash anywhere in path (/foo\\bar)", () => {
    expect(safeRedirectPath("/foo\\bar")).toBe("/");
  });
});

describe("GET /auth/callback", () => {
  beforeEach(() => {
    mockExchangeCodeForSession.mockReset();
    mockCreateClient.mockReset();
  });

  async function callHandler(url: string) {
    const { GET } = await import("./callback");
    const request = new Request(url);
    return GET({ request } as any);
  }

  it("redirects to /login when no code param is present", async () => {
    const response = await callHandler("http://localhost/auth/callback");

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/login");
    expect(mockCreateClient).not.toHaveBeenCalled();
  });

  it("redirects to /login when code param is empty", async () => {
    const response = await callHandler("http://localhost/auth/callback?code=");

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/login");
  });

  it("redirects to / on successful code exchange", async () => {
    mockExchangeCodeForSession.mockResolvedValue({ error: null });
    mockCreateClient.mockReturnValue({
      auth: { exchangeCodeForSession: mockExchangeCodeForSession },
    });

    const response = await callHandler(
      "http://localhost/auth/callback?code=abc123"
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/");
    expect(mockExchangeCodeForSession).toHaveBeenCalledWith("abc123");
  });

  it("redirects to next param on successful exchange", async () => {
    mockExchangeCodeForSession.mockResolvedValue({ error: null });
    mockCreateClient.mockReturnValue({
      auth: { exchangeCodeForSession: mockExchangeCodeForSession },
    });

    const response = await callHandler(
      "http://localhost/auth/callback?code=abc123&next=/dashboard"
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/dashboard");
  });

  it("redirects to /login when code exchange fails", async () => {
    mockExchangeCodeForSession.mockResolvedValue({
      error: new Error("invalid code"),
    });
    mockCreateClient.mockReturnValue({
      auth: { exchangeCodeForSession: mockExchangeCodeForSession },
    });

    const response = await callHandler(
      "http://localhost/auth/callback?code=bad"
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/login");
  });

  it("sets cookies from supabase client via response headers", async () => {
    mockExchangeCodeForSession.mockResolvedValue({ error: null });
    mockCreateClient.mockImplementation(
      (_request: Request, responseHeaders: Headers) => {
        responseHeaders.append("Set-Cookie", "sb-token=abc; Path=/; HttpOnly");
        return {
          auth: { exchangeCodeForSession: mockExchangeCodeForSession },
        };
      }
    );

    const response = await callHandler(
      "http://localhost/auth/callback?code=abc123"
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("Set-Cookie")).toContain("sb-token=abc");
  });

  it("sanitizes malicious next param via safeRedirectPath", async () => {
    mockExchangeCodeForSession.mockResolvedValue({ error: null });
    mockCreateClient.mockReturnValue({
      auth: { exchangeCodeForSession: mockExchangeCodeForSession },
    });

    const response = await callHandler(
      "http://localhost/auth/callback?code=abc123&next=https://evil.com"
    );

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/");
  });
});
