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

  test("renders three marketing nav links and one dropdown trigger", async ({ page }) => {
    await expect(page.locator("nav").getByRole("link", { name: "Home" })).toBeVisible();
    await expect(page.locator("nav").getByRole("link", { name: "Pricing" })).toBeVisible();
    await expect(page.locator("nav").getByRole("button", { name: /open tools/i })).toBeVisible();
    await expect(page.locator("nav").getByRole("link", { name: "Blog" })).toBeVisible();
  });

  test("nav links point to marketing-site URLs", async ({ page }) => {
    await expect(page.locator("nav").getByRole("link", { name: "Home" })).toHaveAttribute(
      "href",
      "https://opennotes.ai",
    );
    await expect(page.locator("nav").getByRole("link", { name: "Pricing" })).toHaveAttribute(
      "href",
      "https://opennotes.ai/pricing",
    );
    await expect(page.locator("nav").getByRole("link", { name: "Blog" })).toHaveAttribute(
      "href",
      "https://opennotes.ai/#blog",
    );
  });

  test("Open Tools dropdown reveals sub-items when clicked", async ({ page }) => {
    await page.locator("nav").getByRole("button", { name: /open tools/i }).click();
    await expect(page.getByRole("link", { name: "Discord Bot" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Playground" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Free Eval" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Vibe Check" })).toBeVisible();
  });

  test("Sign In link is present in the nav actions slot (actions unchanged)", async ({
    page,
  }) => {
    await expect(
      page.locator("nav").getByRole("link", { name: /Sign In/i }),
    ).toBeVisible();
  });

  test("nav links carry text-foreground class (not muted-foreground)", async ({
    page,
  }) => {
    const link = page.getByRole("link", { name: "Pricing" });
    const className = await link.getAttribute("class");
    expect(className).toContain("text-foreground");
    expect(className).not.toContain("text-muted-foreground");
  });

  test("nav links carry hover:text-primary class (not hover:text-foreground)", async ({
    page,
  }) => {
    const link = page.getByRole("link", { name: "Pricing" });
    const className = await link.getAttribute("class");
    expect(className).toContain("hover:text-primary");
    expect(className).not.toContain("hover:text-foreground");
  });

  test("nav items are right-aligned (flex-1 spacer pushes them beside actions)", async ({
    page,
  }) => {
    const nav = page.locator("nav").first();
    const homeLink = nav.getByRole("link", { name: "Home" });
    const signIn = nav.getByRole("link", { name: /Sign In/i });
    const navBox = await nav.boundingBox();
    const homeBox = await homeLink.boundingBox();
    const signInBox = await signIn.boundingBox();
    const navMidX = navBox!.x + navBox!.width / 2;
    expect(homeBox!.x).toBeGreaterThan(navMidX);
    expect(homeBox!.x).toBeLessThan(signInBox!.x);
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
