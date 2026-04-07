import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { OAuthButtons } from "./OAuthButtons";

const mockSignInWithOAuth = vi.fn().mockResolvedValue({ data: {}, error: null });

vi.mock("~/lib/supabase-browser", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: mockSignInWithOAuth,
    },
  }),
}));

describe("OAuthButtons", () => {
  beforeEach(() => {
    mockSignInWithOAuth.mockClear();
    Object.defineProperty(window, "location", {
      value: { origin: "http://localhost:3000" },
      writable: true,
    });
  });

  it("renders Google and X sign-in buttons", () => {
    render(() => <OAuthButtons />);

    expect(screen.getByRole("button", { name: /google/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /\bx\b/i })).toBeDefined();
  });

  it("calls signInWithOAuth with google provider on click", async () => {
    render(() => <OAuthButtons />);

    const googleButton = screen.getByRole("button", { name: /google/i });
    await fireEvent.click(googleButton);

    expect(mockSignInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: "http://localhost:3000/auth/callback?next=%2F",
      },
    });
  });

  it("calls signInWithOAuth with twitter provider on click", async () => {
    render(() => <OAuthButtons />);

    const xButton = screen.getByRole("button", { name: /\bx\b/i });
    await fireEvent.click(xButton);

    expect(mockSignInWithOAuth).toHaveBeenCalledWith({
      provider: "twitter",
      options: {
        redirectTo: "http://localhost:3000/auth/callback?next=%2F",
        scopes: "users.read tweet.read",
      },
    });
  });

  it("passes returnTo through to redirectTo", async () => {
    render(() => <OAuthButtons returnTo="/dashboard" />);

    const googleButton = screen.getByRole("button", { name: /google/i });
    await fireEvent.click(googleButton);

    expect(mockSignInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: "http://localhost:3000/auth/callback?next=%2Fdashboard",
      },
    });
  });

  it("defaults returnTo to / when not provided", async () => {
    render(() => <OAuthButtons />);

    const googleButton = screen.getByRole("button", { name: /google/i });
    await fireEvent.click(googleButton);

    expect(mockSignInWithOAuth).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          redirectTo: expect.stringContaining("next=%2F"),
        }),
      })
    );
  });

  it("renders a separator between buttons and form area", () => {
    render(() => <OAuthButtons />);

    expect(screen.getByText("or")).toBeDefined();
  });
});
