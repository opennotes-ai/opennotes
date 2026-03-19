import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGetRequestEvent, mockRedirect } = vi.hoisted(() => ({
  mockGetRequestEvent: vi.fn(),
  mockRedirect: vi.fn((path: string) => {
    const err = new Response(null, {
      status: 302,
      headers: { Location: path },
    });
    return err;
  }),
}));

vi.mock("solid-js/web", () => ({
  getRequestEvent: mockGetRequestEvent,
}));

vi.mock("@solidjs/router", () => ({
  redirect: mockRedirect,
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("requireAuth", () => {
  it("returns user when event.locals.user is set", async () => {
    const fakeUser = { id: "user-789", email: "auth@example.com" };
    mockGetRequestEvent.mockReturnValue({
      locals: { user: fakeUser },
    });

    const { requireAuth } = await import("./auth-guard");
    const user = await requireAuth();

    expect(user).toEqual(fakeUser);
  });

  it("throws redirect to /login when event.locals.user is null", async () => {
    mockGetRequestEvent.mockReturnValue({
      locals: { user: null },
    });

    const { requireAuth } = await import("./auth-guard");

    await expect(requireAuth()).rejects.toBeDefined();
    expect(mockRedirect).toHaveBeenCalledWith("/login");
  });

  it("throws redirect to /login when getRequestEvent returns undefined", async () => {
    mockGetRequestEvent.mockReturnValue(undefined);

    const { requireAuth } = await import("./auth-guard");

    await expect(requireAuth()).rejects.toBeDefined();
    expect(mockRedirect).toHaveBeenCalledWith("/login");
  });
});
