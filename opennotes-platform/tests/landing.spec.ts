// Landing page E2E spec for opennotes-platform.
//
// NOTE: opennotes-platform does not yet ship @playwright/test in its
// devDependencies (TASK-1503.10 will wire it up). The visual + behavioral
// verification for TASK-1503.09 was performed via the shared `playwright`
// skill against the running `pnpm dev` server (port 3200) — see TASK-1503
// implementation notes for the screenshots and recorded checks.
//
// This file is the canonical source of truth for the scenarios that should
// run automatically once Playwright is wired in. Keep it in sync with the
// landing page (src/routes/index.tsx) so the follow-up task can drop in
// the test runner with no further edits.

import { test, expect } from "@playwright/test";

test.describe("/ landing page (anonymous)", () => {
  test("renders hero, steps, audience cards, and CTAs", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText(/Community-powered moderation/i)).toBeVisible();

    for (const step of [
      "Create your account",
      "Generate your API key",
      "Send your first request",
      "Get results automatically",
      "Plug into your workflow",
    ]) {
      await expect(page.getByText(step)).toBeVisible();
    }

    await expect(
      page.getByRole("link", { name: /Discourse setup/i }),
    ).toHaveAttribute("href", /docs\.opennotes\.ai\/existing-integrations/);
    await expect(
      page.getByRole("link", { name: /Integration guide/i }),
    ).toHaveAttribute("href", /docs\.opennotes\.ai\/integration-guide/);
    await expect(
      page.getByRole("link", { name: /API reference/i }),
    ).toHaveAttribute("href", /docs\.opennotes\.ai\/api-reference/);

    await expect(page.locator('a[href="/register"]').first()).toBeVisible();
    await expect(page.locator('a[href="/login"]').first()).toBeVisible();
  });

  test("docs links open in same tab (no target=_blank)", async ({ page }) => {
    await page.goto("/");
    const docsLinks = await page
      .locator('a[href*="docs.opennotes.ai"]')
      .all();
    expect(docsLinks.length).toBeGreaterThan(0);
    for (const link of docsLinks) {
      expect(await link.getAttribute("target")).not.toBe("_blank");
    }
  });

  test("logo renders from canonical GCS URL", async ({ page }) => {
    await page.goto("/");
    const logo = page.locator('nav img[alt="Open Notes"]');
    await expect(logo).toBeVisible();
    const src = await logo.getAttribute("src");
    expect(src).toContain("open-notes-core-public-assets/opennotes-logo.svg");
  });
});

test.describe("/ landing page typography", () => {
  test("desktop H1 fits design budget (≤56px)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const fontSize = await page
      .locator("h1")
      .first()
      .evaluate((el) => window.getComputedStyle(el).fontSize);
    expect(parseFloat(fontSize)).toBeLessThanOrEqual(56);
  });

  test("mobile H1 stays in expected range (28-40px)", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    const fontSize = await page
      .locator("h1")
      .first()
      .evaluate((el) => window.getComputedStyle(el).fontSize);
    const px = parseFloat(fontSize);
    expect(px).toBeGreaterThanOrEqual(28);
    expect(px).toBeLessThanOrEqual(40);
  });
});

test.describe("/ landing page (authenticated)", () => {
  // Skipped until Supabase test-user fixtures are wired in (follow-up task).
  test.skip("authenticated visitor is redirected to /dashboard", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.fill(
      'input[name="email"]',
      process.env.TEST_USER_EMAIL ?? "test@example.com",
    );
    await page.fill(
      'input[name="password"]',
      process.env.TEST_USER_PASSWORD ?? "password",
    );
    await page.click('button[type="submit"]');
    await page.waitForURL("**/dashboard");
    await page.goto("/");
    await page.waitForURL("**/dashboard");
    expect(page.url()).toContain("/dashboard");
  });
});

test.describe("signout flow", () => {
  test("anonymous home shows Sign In, not Sign Out", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("link", { name: /Sign In/i }),
    ).toBeVisible();
    // Catch any regression that renders Sign Out as a link or plain text,
    // not just as the current submit button.
    await expect(page.getByText(/^Sign Out$/i)).toHaveCount(0);
  });

  // Skipped until Supabase test-user fixtures are wired in (TASK-1503.10).
  // Authed visitors to / are redirected to /dashboard, so we verify Sign Out
  // on the dashboard NavBar — the root layout renders the same auth-aware
  // actions on every route.
  test.skip("signed-in user sees Sign Out on shared layout", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.fill(
      'input[name="email"]',
      process.env.TEST_USER_EMAIL ?? "test@example.com",
    );
    await page.fill(
      'input[name="password"]',
      process.env.TEST_USER_PASSWORD ?? "password",
    );
    await page.click('button[type="submit"]');
    await page.waitForURL("**/dashboard");
    await expect(
      page.getByRole("button", { name: /Sign Out/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Sign In/i }),
    ).toHaveCount(0);
  });

  // Skipped until Supabase test-user fixtures are wired in (TASK-1503.10).
  test.skip(
    "clicking Sign Out returns to anonymous home and clears session",
    async ({ page }) => {
      await page.goto("/login");
      await page.fill(
        'input[name="email"]',
        process.env.TEST_USER_EMAIL ?? "test@example.com",
      );
      await page.fill(
        'input[name="password"]',
        process.env.TEST_USER_PASSWORD ?? "password",
      );
      await page.click('button[type="submit"]');
      await page.waitForURL("**/dashboard");

      await page.getByRole("button", { name: /Sign Out/i }).click();
      await page.waitForURL("**/");

      await expect(
        page.getByRole("link", { name: /Sign In/i }),
      ).toBeVisible();

      // Fresh page load still shows Sign In — confirms the cookie clear
      // is durable (assert observable UI state, not Supabase cookie names).
      await page.reload();
      await expect(
        page.getByRole("link", { name: /Sign In/i }),
      ).toBeVisible();

      // Re-visiting an authed-only route should not stay on /dashboard.
      await page.goto("/dashboard");
      expect(page.url()).not.toContain("/dashboard");
    },
  );

  // Skipped until Supabase test-user fixtures are wired in (TASK-1503.10).
  // Sanity-check that dark-mode color scheme does not hide the Sign Out
  // button. No screenshot diff (visual baselines are out of scope here —
  // see TASK-1468.17). We first assert the dark theme actually activated
  // (ModeToggle reads prefers-color-scheme and toggles `.dark` on
  // documentElement), then assert the button still renders.
  test.skip(
    "Sign Out button renders under dark color scheme",
    async ({ page }) => {
      await page.emulateMedia({ colorScheme: "dark" });
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto("/login");
      await page.fill(
        'input[name="email"]',
        process.env.TEST_USER_EMAIL ?? "test@example.com",
      );
      await page.fill(
        'input[name="password"]',
        process.env.TEST_USER_PASSWORD ?? "password",
      );
      await page.click('button[type="submit"]');
      await page.waitForURL("**/dashboard");
      // Confirm dark theme actually took effect — without this the test
      // would silently pass even if `.dark` never got applied.
      await expect(page.locator("html")).toHaveClass(/(^|\s)dark(\s|$)/);
      await expect(
        page.getByRole("button", { name: /Sign Out/i }),
      ).toBeVisible();
    },
  );
});
