import { afterEach, describe, expect, test, vi } from "vitest";

vi.mock("solid-js/web", () => ({
  getRequestEvent: vi.fn(),
}));

vi.mock("@solidjs/router", () => ({
  redirect: (target: string) => {
    const err = new Error(`redirect to ${target}`) as Error & {
      status: number;
      headers: { location: string };
    };
    err.status = 302;
    err.headers = { location: target };
    return err;
  },
}));

import { getRequestEvent } from "solid-js/web";
import { redirectIfAuthenticated } from "./auth-guard";

const mockedGetRequestEvent = vi.mocked(getRequestEvent);

afterEach(() => {
  mockedGetRequestEvent.mockReset();
});

describe("redirectIfAuthenticated", () => {
  test("throws redirect to /dashboard when user is set", async () => {
    mockedGetRequestEvent.mockReturnValue({
      locals: { user: { id: "user-1" } },
    } as unknown as ReturnType<typeof getRequestEvent>);

    await expect(redirectIfAuthenticated()).rejects.toMatchObject({
      status: 302,
      headers: { location: "/dashboard" },
    });
  });

  test("throws redirect to custom target when provided", async () => {
    mockedGetRequestEvent.mockReturnValue({
      locals: { user: { id: "user-1" } },
    } as unknown as ReturnType<typeof getRequestEvent>);

    await expect(redirectIfAuthenticated("/onboarding")).rejects.toMatchObject({
      status: 302,
      headers: { location: "/onboarding" },
    });
  });

  test("returns silently when user is null", async () => {
    mockedGetRequestEvent.mockReturnValue({
      locals: { user: null },
    } as unknown as ReturnType<typeof getRequestEvent>);

    await expect(redirectIfAuthenticated()).resolves.toBeUndefined();
  });

  test("returns silently when no request event (e.g. client-side hydration)", async () => {
    mockedGetRequestEvent.mockReturnValue(undefined);

    await expect(redirectIfAuthenticated()).resolves.toBeUndefined();
  });
});
