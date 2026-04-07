import { test, expect, type Route } from "@playwright/test";

const AUTHORIZE_PATTERN = "https://*.supabase.co/auth/v1/authorize**";

function interceptOAuthRedirect(page: import("@playwright/test").Page) {
  let captured: URL | null = null;
  const ready = page.route(AUTHORIZE_PATTERN, (route: Route) => {
    captured = new URL(route.request().url());
    return route.fulfill({ status: 200, body: "intercepted" });
  });
  return {
    ready,
    url: () => captured,
  };
}

test.describe("OAuth login flow", () => {
  test.describe("login page", () => {
    test("Google button redirects to Supabase with provider=google", async ({
      page,
    }) => {
      const intercept = interceptOAuthRedirect(page);
      await intercept.ready;

      await page.goto("/login", { waitUntil: "networkidle" });

      const googleButton = page.getByRole("button", {
        name: /sign in with google/i,
      });
      await expect(googleButton).toBeVisible();
      await googleButton.click();

      await page.waitForURL((url) => url.hostname !== "localhost", {
        timeout: 10_000,
      }).catch(() => {});

      const redirectUrl = intercept.url();
      expect(redirectUrl).not.toBeNull();
      expect(redirectUrl!.hostname).toMatch(/\.supabase\.co$/);
      expect(redirectUrl!.pathname).toBe("/auth/v1/authorize");
      expect(redirectUrl!.searchParams.get("provider")).toBe("google");
    });

    test("X button redirects to Supabase with provider=twitter", async ({
      page,
    }) => {
      const intercept = interceptOAuthRedirect(page);
      await intercept.ready;

      await page.goto("/login", { waitUntil: "networkidle" });

      const xButton = page.getByRole("button", {
        name: /sign in with x/i,
      });
      await expect(xButton).toBeVisible();
      await xButton.click();

      await page.waitForURL((url) => url.hostname !== "localhost", {
        timeout: 10_000,
      }).catch(() => {});

      const redirectUrl = intercept.url();
      expect(redirectUrl).not.toBeNull();
      expect(redirectUrl!.hostname).toMatch(/\.supabase\.co$/);
      expect(redirectUrl!.pathname).toBe("/auth/v1/authorize");
      expect(redirectUrl!.searchParams.get("provider")).toBe("twitter");
    });

    test("returnTo parameter is preserved in OAuth redirect URL", async ({
      page,
    }) => {
      const intercept = interceptOAuthRedirect(page);
      await intercept.ready;

      await page.goto("/login?returnTo=/simulations/123", {
        waitUntil: "networkidle",
      });

      const googleButton = page.getByRole("button", {
        name: /sign in with google/i,
      });
      await googleButton.click();

      await page.waitForURL((url) => url.hostname !== "localhost", {
        timeout: 10_000,
      }).catch(() => {});

      const redirectUrl = intercept.url();
      expect(redirectUrl).not.toBeNull();

      const redirectTo = redirectUrl!.searchParams.get("redirect_to");
      expect(redirectTo).not.toBeNull();
      expect(redirectTo).toContain("next=");
      expect(redirectTo).toContain(encodeURIComponent("/simulations/123"));
    });

    test("email and password form renders and accepts input", async ({
      page,
    }) => {
      await page.goto("/login", { waitUntil: "networkidle" });

      const emailInput = page.locator('input[name="email"]');
      const passwordInput = page.locator('input[name="password"]');
      const submitButton = page.getByRole("button", { name: /sign in$/i });

      await expect(emailInput).toBeVisible();
      await expect(passwordInput).toBeVisible();
      await expect(submitButton).toBeVisible();

      await emailInput.fill("test@example.com");
      await passwordInput.fill("password123");

      await expect(emailInput).toHaveValue("test@example.com");
      await expect(passwordInput).toHaveValue("password123");
    });
  });

  test.describe("register page", () => {
    test("OAuth buttons appear on register page", async ({ page }) => {
      await page.goto("/register", { waitUntil: "networkidle" });

      const googleButton = page.getByRole("button", {
        name: /sign in with google/i,
      });
      const xButton = page.getByRole("button", {
        name: /sign in with x/i,
      });

      await expect(googleButton).toBeVisible();
      await expect(xButton).toBeVisible();
    });

    test("Google button on register page redirects to Supabase", async ({
      page,
    }) => {
      const intercept = interceptOAuthRedirect(page);
      await intercept.ready;

      await page.goto("/register", { waitUntil: "networkidle" });

      const googleButton = page.getByRole("button", {
        name: /sign in with google/i,
      });
      await googleButton.click();

      await page.waitForURL((url) => url.hostname !== "localhost", {
        timeout: 10_000,
      }).catch(() => {});

      const redirectUrl = intercept.url();
      expect(redirectUrl).not.toBeNull();
      expect(redirectUrl!.hostname).toMatch(/\.supabase\.co$/);
      expect(redirectUrl!.searchParams.get("provider")).toBe("google");
    });
  });
});
