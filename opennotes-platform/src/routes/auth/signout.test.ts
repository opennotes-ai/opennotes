import { afterEach, describe, expect, test, vi } from "vitest";

const signOutMock = vi.fn();
const createClientMock = vi.fn();

vi.mock("~/lib/supabase-server", () => ({
  createClient: (...args: unknown[]) => createClientMock(...args),
}));

import { DELETE, GET, OPTIONS, PATCH, POST, PUT } from "./signout";

afterEach(() => {
  signOutMock.mockReset();
  createClientMock.mockReset();
});

function buildSupabaseClient(
  responseHeaders: Headers,
  setCookies: Array<[string, string]> = [
    ["sb-access-token", "; Max-Age=0; Path=/"],
    ["sb-refresh-token", "; Max-Age=0; Path=/"],
  ]
) {
  signOutMock.mockImplementation(async () => {
    for (const [name, rest] of setCookies) {
      responseHeaders.append("Set-Cookie", `${name}=${rest}`);
    }
    return { error: null };
  });
  return { auth: { signOut: signOutMock } };
}

function buildRequest(method: string = "POST"): Request {
  return new Request("https://platform.opennotes.ai/auth/signout", {
    method,
    headers: { Cookie: "sb-access-token=token-value" },
  });
}

describe("POST /auth/signout", () => {
  test("returns 303 redirect to /", async () => {
    createClientMock.mockImplementation(
      (_request: Request, responseHeaders: Headers) =>
        buildSupabaseClient(responseHeaders)
    );

    const response = await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/");
  });

  test("invokes supabase.auth.signOut() exactly once on the SSR client", async () => {
    createClientMock.mockImplementation(
      (_request: Request, responseHeaders: Headers) =>
        buildSupabaseClient(responseHeaders)
    );

    await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    expect(signOutMock).toHaveBeenCalledTimes(1);
  });

  test("propagates Set-Cookie headers issued by the SSR signOut flow", async () => {
    createClientMock.mockImplementation(
      (_request: Request, responseHeaders: Headers) =>
        buildSupabaseClient(responseHeaders)
    );

    const response = await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    const setCookie = response.headers.get("Set-Cookie") ?? "";
    expect(setCookie).toMatch(/sb-/);
  });

  test("still returns 303 to / when supabase reports no active session", async () => {
    createClientMock.mockImplementation(
      (_request: Request, _responseHeaders: Headers) => ({
        auth: {
          signOut: vi.fn(async () => ({
            error: { name: "AuthSessionMissingError" },
          })),
        },
      })
    );

    const response = await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/");
  });
});

describe("non-POST methods on /auth/signout", () => {
  test.each([
    ["GET", GET],
    ["PUT", PUT],
    ["PATCH", PATCH],
    ["DELETE", DELETE],
    ["OPTIONS", OPTIONS],
  ])("%s returns 405 Method Not Allowed with Allow: POST", async (_name, handler) => {
    const response = await handler();

    expect(response.status).toBe(405);
    expect(response.headers.get("Allow")).toBe("POST");
  });
});
