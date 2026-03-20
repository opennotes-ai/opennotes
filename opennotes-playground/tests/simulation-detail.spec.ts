import { test, expect } from "@playwright/test";

const SIM_URL = "/simulations/019ceaaf-487e-708f-bcae-e4a441d6e841";

const EXPECTED_SECTIONS = [
  "Agents",
  "Notes & Ratings",
  "Scoring & Analysis",
  "Note Details",
  "Chat Channel",
];

test.describe("Simulation detail page", () => {
  test.describe("desktop viewport", () => {
    test.use({ viewport: { width: 1280, height: 720 } });

    test("sidebar shows exactly 5 sections", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const sidebarButtons = page.locator("aside nav button");
      await expect(sidebarButtons).toHaveCount(5);

      for (let i = 0; i < EXPECTED_SECTIONS.length; i++) {
        await expect(sidebarButtons.nth(i)).toHaveText(EXPECTED_SECTIONS[i]);
      }
    });

    test("clicking sidebar link scrolls to correct section", async ({
      page,
    }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      await page.locator("aside nav button", { hasText: "Agents" }).click();
      await expect(page.locator("section#agents")).toBeInViewport();

      await page
        .locator("aside nav button", { hasText: "Notes & Ratings" })
        .click();
      await expect(page.locator("section#notes-ratings")).toBeInViewport();
    });

    test("no Simulation Mechanics text on page", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });
      await expect(page.getByText("Simulation Mechanics")).toHaveCount(0);
    });

    test("no inline TOC element on page", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });
      const inlineToc = page.locator('nav[aria-label="Table of contents"]');
      await expect(inlineToc).toHaveCount(0);
    });

    test("badges in tables have font-size >= 11px", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const badges = page.locator("section#agents table span");
      const count = await badges.count();
      expect(count).toBeGreaterThan(0);

      for (let i = 0; i < Math.min(count, 5); i++) {
        const fontSize = await badges.nth(i).evaluate(
          (el) => parseFloat(getComputedStyle(el).fontSize),
        );
        expect(fontSize).toBeGreaterThanOrEqual(11);
      }
    });

    test("chart canvas renders in notes-ratings section", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const canvas = page.locator("section#notes-ratings canvas").first();
      await expect(canvas).toBeVisible({ timeout: 10_000 });
    });

    test("per-note ratings are collapsed by default", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const ratingDetails = page.locator("section#note-details details.mt-3");
      const count = await ratingDetails.count();

      if (count > 0) {
        for (let i = 0; i < Math.min(count, 5); i++) {
          const isOpen = await ratingDetails.nth(i).getAttribute("open");
          expect(isOpen).toBeNull();
        }
      }
    });

    test("per-agent histogram renders", async ({ page }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const histogramCanvas = page.locator("section#agents canvas");
      await expect(histogramCanvas.first()).toBeVisible({ timeout: 10_000 });
    });
  });

  test.describe("mobile viewport", () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test("hamburger button visible, opens drawer with section links", async ({
      page,
    }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const aside = page.locator("aside");
      await expect(aside).toBeHidden();

      const hamburger = page.locator('button[aria-label="Open navigation"]');
      await expect(hamburger).toBeVisible();
      await hamburger.click();

      const drawer = page.locator('[role="dialog"]');
      await expect(drawer).toBeVisible();

      const drawerButtons = drawer.locator("nav button");
      await expect(drawerButtons).toHaveCount(5);

      for (let i = 0; i < EXPECTED_SECTIONS.length; i++) {
        await expect(drawerButtons.nth(i)).toHaveText(EXPECTED_SECTIONS[i]);
      }
    });

    test("mobile drawer section links scroll to sections", async ({
      page,
    }) => {
      await page.goto(SIM_URL, { waitUntil: "networkidle" });

      const hamburger = page.locator('button[aria-label="Open navigation"]');
      await hamburger.click();

      const drawer = page.locator('[role="dialog"]');
      await expect(drawer).toBeVisible();

      await drawer
        .locator("nav button", { hasText: "Scoring & Analysis" })
        .click();

      await expect(page.locator("section#scoring-analysis")).toBeInViewport({
        timeout: 5_000,
      });
    });
  });
});
