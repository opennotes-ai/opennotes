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

  test("logo is served at /opennotes-logo.svg", async ({ page }) => {
    const resp = await page.goto("/opennotes-logo.svg");
    expect(resp?.status()).toBe(200);
    expect(resp?.headers()["content-type"]).toMatch(/svg/);
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
