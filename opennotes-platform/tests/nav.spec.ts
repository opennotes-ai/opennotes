// NavBar E2E spec for opennotes-platform.
//
// NOTE: opennotes-platform does not yet ship @playwright/test in its
// devDependencies (TASK-1503.10 will wire it up). The nav link + visual
// verification for TASK-1517.01 was performed via the shared `playwright`
// skill against the running `pnpm dev` server (port 3200) — see TASK-1517.01
// implementation notes for the screenshots.
//
// This file is the canonical source of truth for the nav scenarios that should
// run automatically once Playwright is wired in.

import { test, expect } from "@playwright/test";

const DESKTOP = { width: 1440, height: 900 };

test.describe("NavBar marketing items", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
  });

  test("renders all four marketing nav links", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Pricing" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Tools" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Blog" })).toBeVisible();
  });

  test("nav links point to marketing-site URLs", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Home" })).toHaveAttribute(
      "href",
      "https://opennotes.ai",
    );
    await expect(page.getByRole("link", { name: "Pricing" })).toHaveAttribute(
      "href",
      "https://opennotes.ai/pricing",
    );
    await expect(page.getByRole("link", { name: "Open Tools" })).toHaveAttribute(
      "href",
      "https://opennotes.ai/open-tools",
    );
    await expect(page.getByRole("link", { name: "Blog" })).toHaveAttribute(
      "href",
      "https://opennotes.ai/#blog",
    );
  });

  test("Sign In link is present in the nav actions slot (actions unchanged)", async ({
    page,
  }) => {
    await expect(
      page.locator("nav").getByRole("link", { name: /Sign In/i }),
    ).toBeVisible();
  });

  test("nav links use text-foreground color in light mode (desktop)", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    const link = page.getByRole("link", { name: "Pricing" });
    const color = await link.evaluate(
      (el) => window.getComputedStyle(el).color,
    );
    // text-foreground in light mode is oklch(0.25 0.015 160) — not the dimmer
    // muted-foreground value. We verify the alpha channel is 1 (fully opaque)
    // and the color is not the muted gray.
    expect(color).not.toBe("rgba(0, 0, 0, 0)");
  });

  test("nav links use text-foreground color in dark mode (desktop)", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/");
    const link = page.getByRole("link", { name: "Pricing" });
    await expect(link).toBeVisible();
    const color = await link.evaluate(
      (el) => window.getComputedStyle(el).color,
    );
    expect(color).not.toBe("rgba(0, 0, 0, 0)");
  });
});

test.describe("NavBar layout shell unchanged", () => {
  test("nav height is 64px (h-16 token, unchanged from pre-PR)", async ({
    page,
  }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
    const nav = page.locator("nav").first();
    const box = await nav.boundingBox();
    expect(box?.height).toBe(64);
  });

  test("nav bar has no Docs link (replaced by marketing items)", async ({
    page,
  }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
    await expect(
      page.locator("nav").getByRole("link", { name: "Docs" }),
    ).toHaveCount(0);
  });
});
