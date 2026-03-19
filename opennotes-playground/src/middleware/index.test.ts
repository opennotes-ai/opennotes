import { describe, it, expect, vi, beforeEach } from "vitest";

let capturedOnRequest: (event: any) => Promise<void>;

const { mockGetUser, mockCreateClient, mockCreateReadOnlyClient, mockReadOnlyClient } =
  vi.hoisted(() => {
    const mockGetUser = vi.fn();
    const mockCreateClient = vi.fn(() => ({ auth: { getUser: mockGetUser } }));
    const mockReadOnlyClient = { __readOnly: true };
    const mockCreateReadOnlyClient = vi.fn(() => mockReadOnlyClient);
    return { mockGetUser, mockCreateClient, mockCreateReadOnlyClient, mockReadOnlyClient };
  });

vi.mock("@solidjs/start/middleware", () => ({
  createMiddleware: (config: { onRequest: (event: any) => Promise<void> }) => {
    capturedOnRequest = config.onRequest;
    return config;
  },
}));

vi.mock("~/lib/supabase-server", () => ({
  createClient: mockCreateClient,
  createReadOnlyClient: mockCreateReadOnlyClient,
}));

function createMockEvent() {
  return {
    request: new Request("http://localhost/test"),
    response: { headers: new Headers() },
    locals: {} as Record<string, any>,
  };
}

describe("middleware onRequest", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await import("./index.js");
  });

  it("sets event.locals.user to User when getUser succeeds", async () => {
    const fakeUser = { id: "user-123", email: "test@example.com" };
    mockGetUser.mockResolvedValue({ data: { user: fakeUser } });

    const event = createMockEvent();
    await capturedOnRequest(event);

    expect(event.locals.user).toEqual(fakeUser);
  });

  it("sets event.locals.user to null when getUser returns no user", async () => {
    mockGetUser.mockResolvedValue({ data: { user: null } });

    const event = createMockEvent();
    await capturedOnRequest(event);

    expect(event.locals.user).toBeNull();
  });

  it("sets event.locals.user to null when getUser throws and logs the error", async () => {
    const authError = new Error("Auth session expired");
    mockGetUser.mockRejectedValue(authError);
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const event = createMockEvent();
    await capturedOnRequest(event);

    expect(event.locals.user).toBeNull();
    expect(consoleSpy).toHaveBeenCalledWith("Middleware auth error:", authError);
    consoleSpy.mockRestore();
  });

  it("always sets event.locals.supabase to the read-only client", async () => {
    mockGetUser.mockResolvedValue({ data: { user: null } });

    const event = createMockEvent();
    await capturedOnRequest(event);

    expect(event.locals.supabase).toBe(mockReadOnlyClient);
    expect(mockCreateReadOnlyClient).toHaveBeenCalledWith(event.request);
  });

  it("sets event.locals.supabase even when auth throws", async () => {
    mockGetUser.mockRejectedValue(new Error("Auth failed"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const event = createMockEvent();
    await capturedOnRequest(event);

    expect(event.locals.supabase).toBe(mockReadOnlyClient);
    expect(mockCreateReadOnlyClient).toHaveBeenCalledWith(event.request);
  });
});
