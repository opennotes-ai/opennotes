import { describe, expect, it, vi, beforeEach } from "vitest";

let capturedCookies: any = null;
const mockClient = { auth: { getUser: vi.fn() } };

const { mockGetRequestEvent } = vi.hoisted(() => ({
  mockGetRequestEvent: vi.fn(),
}));

vi.mock("@supabase/ssr", () => ({
  createServerClient: vi.fn((_url: string, _key: string, opts: any) => {
    capturedCookies = opts.cookies;
    return mockClient;
  }),
  parseCookieHeader: vi.fn((header: string) => {
    if (!header) return [];
    return header.split("; ").map((pair) => {
      const [name, ...rest] = pair.split("=");
      return { name, value: rest.join("=") };
    });
  }),
  serializeCookieHeader: vi.fn(),
}));

vi.mock("solid-js/web", () => ({
  getRequestEvent: mockGetRequestEvent,
}));

beforeEach(() => {
  capturedCookies = null;
  vi.clearAllMocks();
  vi.stubEnv("VITE_SUPABASE_URL", "https://test.supabase.co");
  vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "test-anon-key");
});

describe("createReadOnlyClient", () => {
  it("returns a valid Supabase client", async () => {
    const { createReadOnlyClient } = await import("./supabase-server");
    const request = new Request("https://example.com", {
      headers: { Cookie: "sb-token=abc123" },
    });

    const client = createReadOnlyClient(request);

    expect(client).toBe(mockClient);
  });

  it("setAll is a no-op and does not append Set-Cookie headers", async () => {
    const { createReadOnlyClient } = await import("./supabase-server");
    const request = new Request("https://example.com", {
      headers: { Cookie: "sb-token=abc123" },
    });

    createReadOnlyClient(request);

    expect(capturedCookies).not.toBeNull();
    expect(capturedCookies.setAll).toBeTypeOf("function");

    const responseHeaders = new Headers();
    capturedCookies.setAll([
      { name: "sb-token", value: "new-value", options: { path: "/" } },
    ]);

    expect(responseHeaders.has("Set-Cookie")).toBe(false);
  });

  it("throws when env vars are missing", async () => {
    vi.stubEnv("VITE_SUPABASE_URL", "");
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "");

    const { createReadOnlyClient } = await import("./supabase-server");
    const request = new Request("https://example.com");

    expect(() => createReadOnlyClient(request)).toThrow(
      "Missing Supabase config"
    );
  });
});

describe("getUser", () => {
  it("returns user from event.locals when set", async () => {
    const fakeUser = { id: "user-456", email: "hello@example.com" };
    mockGetRequestEvent.mockReturnValue({
      locals: { user: fakeUser },
    });

    const { getUser } = await import("./supabase-server");
    const user = await getUser();

    expect(user).toEqual(fakeUser);
  });

  it("returns null when event.locals.user is null", async () => {
    mockGetRequestEvent.mockReturnValue({
      locals: { user: null },
    });

    const { getUser } = await import("./supabase-server");
    const user = await getUser();

    expect(user).toBeNull();
  });

  it("returns null when getRequestEvent returns undefined", async () => {
    mockGetRequestEvent.mockReturnValue(undefined);

    const { getUser } = await import("./supabase-server");
    const user = await getUser();

    expect(user).toBeNull();
  });
});
