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
    headers: {
      Cookie: "sb-access-token=token-value; sb-refresh-token=refresh-value",
    },
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

  test("propagates Set-Cookie headers issued by the SSR signOut flow", async () => {
    createClientMock.mockImplementation(
      (_request: Request, responseHeaders: Headers) =>
        buildSupabaseClient(responseHeaders)
    );

    const response = await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    const setCookies = response.headers.getSetCookie();
    const access = setCookies.find((c) => c.startsWith("sb-access-token="));
    const refresh = setCookies.find((c) => c.startsWith("sb-refresh-token="));
    expect(access).toBeDefined();
    expect(refresh).toBeDefined();
    expect(access).toMatch(/Max-Age=0/);
    expect(access).toMatch(/Path=\//);
    expect(refresh).toMatch(/Max-Age=0/);
    expect(refresh).toMatch(/Path=\//);
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

  test("unexpected signOut error still clears sb-* cookies on the response", async () => {
    createClientMock.mockImplementation(
      (_request: Request, _responseHeaders: Headers) => ({
        auth: {
          signOut: vi.fn(async () => ({
            error: { name: "AuthApiError", status: 500 },
          })),
        },
      })
    );

    const response = await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/");
    const setCookies = response.headers.getSetCookie();
    const access = setCookies.find((c) => c.startsWith("sb-access-token="));
    const refresh = setCookies.find((c) => c.startsWith("sb-refresh-token="));
    expect(access).toBeDefined();
    expect(refresh).toBeDefined();
    expect(access).toMatch(/Max-Age=0/);
    expect(access).toMatch(/Path=\//);
    expect(refresh).toMatch(/Max-Age=0/);
    expect(refresh).toMatch(/Path=\//);
  });

  test("thrown signOut error still returns 303 + clears cookies (no 500)", async () => {
    createClientMock.mockImplementation(
      (_request: Request, _responseHeaders: Headers) => ({
        auth: {
          signOut: vi.fn(async () => {
            throw new Error("boom");
          }),
        },
      })
    );

    const response = await POST({
      request: buildRequest("POST"),
    } as Parameters<typeof POST>[0]);

    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/");
    const setCookies = response.headers.getSetCookie();
    const access = setCookies.find((c) => c.startsWith("sb-access-token="));
    const refresh = setCookies.find((c) => c.startsWith("sb-refresh-token="));
    expect(access).toBeDefined();
    expect(refresh).toBeDefined();
    expect(access).toMatch(/Max-Age=0/);
    expect(access).toMatch(/Path=\//);
    expect(refresh).toMatch(/Max-Age=0/);
    expect(refresh).toMatch(/Path=\//);
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
