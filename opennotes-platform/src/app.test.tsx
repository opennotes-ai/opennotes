import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getUserMock = vi.fn<() => Promise<unknown>>();

vi.mock("~/lib/supabase-server", () => ({
  getUser: () => getUserMock(),
}));

vi.mock("~/lib/supabase-browser", () => ({
  createClient: () => ({
    auth: {
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
  }),
}));

vi.mock("@solidjs/start/router", () => ({
  FileRoutes: () => null,
}));

vi.mock("@opennotes/ui/components/mode-toggle", () => ({
  default: () => (
    <button type="button" aria-label="Toggle dark mode">
      mode
    </button>
  ),
}));

import { render, screen, waitFor } from "@solidjs/testing-library";
import { Router, query } from "@solidjs/router";
import { RootLayout } from "./app";

beforeEach(() => {
  getUserMock.mockReset();
  query.clear();
});

afterEach(() => {
  document.body.innerHTML = "";
});

const renderWithRouter = () =>
  render(() => (
    <Router root={(props) => <RootLayout>{props.children}</RootLayout>} />
  ));

describe("RootLayout — anonymous state", () => {
  it("renders Sign In link to /login when no user is signed in", async () => {
    getUserMock.mockResolvedValue(null);

    renderWithRouter();

    const signIn = await screen.findByRole("link", { name: /sign in/i });
    expect(signIn).toBeTruthy();
    expect(signIn.getAttribute("href")).toBe("/login");
  });

  it("does not render the Sign Out form when no user is signed in", async () => {
    getUserMock.mockResolvedValue(null);

    const { container } = renderWithRouter();
    await screen.findByRole("link", { name: /sign in/i });

    expect(
      container.querySelector('form[action="/auth/signout"]'),
    ).toBeNull();
  });

  it("renders ModeToggle in the anonymous state", async () => {
    getUserMock.mockResolvedValue(null);

    renderWithRouter();
    await screen.findByRole("link", { name: /sign in/i });

    const modeToggle = screen.getByRole("button", {
      name: /toggle dark mode/i,
    });
    expect(modeToggle).toBeTruthy();
  });
});

describe("RootLayout — signed-in state", () => {
  it("renders a Sign Out form posting to /auth/signout", async () => {
    getUserMock.mockResolvedValue({ id: "u1", email: "a@b.c" });

    const { container } = renderWithRouter();

    await waitFor(() => {
      expect(
        container.querySelector('form[action="/auth/signout"][method="post"]'),
      ).not.toBeNull();
    });
  });

  it("renders a submit button with text Sign Out when user is signed in", async () => {
    getUserMock.mockResolvedValue({ id: "u1", email: "a@b.c" });

    renderWithRouter();

    const signOut = await screen.findByRole("button", { name: /sign out/i });
    expect(signOut).toBeTruthy();
    expect(signOut.getAttribute("type")).toBe("submit");
  });

  it("does not render a Sign In link when user is signed in", async () => {
    getUserMock.mockResolvedValue({ id: "u1", email: "a@b.c" });

    renderWithRouter();
    await screen.findByRole("button", { name: /sign out/i });

    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
  });

  it("renders ModeToggle in the signed-in state", async () => {
    getUserMock.mockResolvedValue({ id: "u1", email: "a@b.c" });

    renderWithRouter();
    await screen.findByRole("button", { name: /sign out/i });

    const modeToggle = screen.getByRole("button", {
      name: /toggle dark mode/i,
    });
    expect(modeToggle).toBeTruthy();
  });

  it("does not flash a Sign In link before the auth resource resolves", async () => {
    let resolveUser!: (user: unknown) => void;
    getUserMock.mockReturnValue(
      new Promise((resolve) => {
        resolveUser = resolve;
      }),
    );

    const { container } = renderWithRouter();

    expect(container.querySelector('a[href="/login"]')).toBeNull();
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();

    resolveUser({ id: "u1" });
    await screen.findByRole("button", { name: /sign out/i });
  });
});
