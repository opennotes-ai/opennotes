import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { signInMock, createClientMock } = vi.hoisted(() => {
  const signInMock = vi.fn();
  const createClientMock = vi.fn(() => ({
    auth: { signInWithPassword: signInMock },
  }));
  return { signInMock, createClientMock };
});

vi.mock("~/lib/supabase-server", () => ({
  createClient: createClientMock,
  getUser: vi.fn(),
}));

vi.mock("@solidjs/start/router", () => ({
  FileRoutes: () => null,
}));

vi.mock("solid-js/web", async (importOriginal) => {
  const actual = await importOriginal<typeof import("solid-js/web")>();
  return {
    ...actual,
    getRequestEvent: vi.fn(),
  };
});

vi.mock("@solidjs/router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@solidjs/router")>();
  return {
    ...actual,
    redirect: (target: string) => {
      const err = new Error(`redirect to ${target}`) as Error & {
        status: number;
        headers: { location: string };
      };
      err.status = 302;
      err.headers = { location: target };
      return err;
    },
    revalidate: vi.fn(async (_key: string) => undefined),
  };
});

import { getRequestEvent } from "solid-js/web";
import { revalidate } from "@solidjs/router";
import { handleLogin } from "./login";
import { NAV_USER_KEY } from "~/app";

const mockedGetRequestEvent = vi.mocked(getRequestEvent);
const mockedRevalidate = vi.mocked(revalidate);

beforeEach(() => {
  signInMock.mockReset();
  createClientMock.mockClear();
  mockedGetRequestEvent.mockReset();
  mockedRevalidate.mockClear();

  mockedGetRequestEvent.mockReturnValue({
    request: new Request("https://example.test/login"),
    response: { headers: new Headers() },
  } as unknown as ReturnType<typeof getRequestEvent>);
});

afterEach(() => {
  vi.restoreAllMocks();
});

const formDataFor = (email: string, password: string) => {
  const fd = new FormData();
  fd.set("email", email);
  fd.set("password", password);
  return fd;
};

describe("handleLogin", () => {
  it("returns 'Email and password are required.' when fields are missing", async () => {
    const result = await handleLogin(formDataFor("", ""));

    expect(result).toBe("Email and password are required.");
    expect(signInMock).not.toHaveBeenCalled();
    expect(mockedRevalidate).not.toHaveBeenCalled();
  });

  it("returns the supabase error message when signInWithPassword fails", async () => {
    signInMock.mockResolvedValue({ error: { message: "Invalid login credentials" } });

    const result = await handleLogin(formDataFor("a@b.c", "wrong"));

    expect(result).toBe("Invalid login credentials");
    expect(mockedRevalidate).not.toHaveBeenCalled();
  });

  it("revalidates the nav-user query before redirecting on success", async () => {
    signInMock.mockResolvedValue({ error: null });

    await expect(handleLogin(formDataFor("a@b.c", "correct"))).rejects.toMatchObject({
      status: 302,
      headers: { location: "/dashboard" },
    });

    expect(mockedRevalidate).toHaveBeenCalledTimes(1);
    expect(mockedRevalidate).toHaveBeenCalledWith(NAV_USER_KEY);
    expect(NAV_USER_KEY).toBe("nav-user");
  });

  it("calls revalidate before throwing the redirect (order check)", async () => {
    signInMock.mockResolvedValue({ error: null });

    const calls: string[] = [];
    mockedRevalidate.mockImplementation(async (key) => {
      calls.push(`revalidate:${String(key)}`);
      return undefined;
    });

    try {
      await handleLogin(formDataFor("a@b.c", "correct"));
    } catch (err) {
      calls.push(`throw:${(err as { headers: { location: string } }).headers.location}`);
    }

    expect(calls).toEqual(["revalidate:nav-user", "throw:/dashboard"]);
  });
});
