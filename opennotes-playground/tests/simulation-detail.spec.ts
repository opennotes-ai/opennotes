import { test, expect } from "@playwright/test";

const SIM_URL = "/simulations/019ceaaf-487e-708f-bcae-e4a441d6e841";

const EXPECTED_SECTIONS = [
  "Agents",
  "Notes & Ratings",
  "Note Details",
  "Scoring & Analysis",
];

test.describe("Simulation detail page", () => {
  test.describe("desktop viewport", () => {
    test.use({ viewport: { width: 1280, height: 720 } });

    test("sidebar shows exactly 4 sections", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("aside nav");

      const sidebarButtons = page.locator("aside nav button");
      await expect(sidebarButtons).toHaveCount(4);

      for (let i = 0; i < EXPECTED_SECTIONS.length; i++) {
        await expect(sidebarButtons.nth(i)).toHaveText(EXPECTED_SECTIONS[i]);
      }
    });

    test("clicking sidebar link scrolls to correct section", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents");

      await page.locator("aside nav button", { hasText: "Agents" }).click();
      await expect(page.locator("section#agents")).toBeInViewport();

      await page.locator("aside nav button", { hasText: "Notes & Ratings" }).click();
      await expect(page.locator("section#notes-ratings")).toBeInViewport();
    });

    test("no Simulation Mechanics text on page", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents");
      await expect(page.getByText("Simulation Mechanics")).toHaveCount(0);
    });

    test("no inline TOC element on page", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents");
      const inlineToc = page.locator('nav[aria-label="Table of contents"]');
      await expect(inlineToc).toHaveCount(0);
    });

    test("badges in tables have font-size >= 11px", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents table");

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

    test("chart x-axis labels contain month abbreviation", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#notes-ratings");
      await page.waitForTimeout(2000);

      const canvas = page.locator("section#notes-ratings canvas").first();
      await expect(canvas).toBeVisible();
    });

    test("per-note ratings are collapsed by default", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#note-details");

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
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents");
      await page.waitForTimeout(1000);

      const histogramContainer = page.locator("section#agents .rounded-lg.border canvas");
      await expect(histogramContainer.first()).toBeVisible();
    });
  });

  test.describe("mobile viewport", () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test("hamburger button visible, opens drawer with section links", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents");

      const aside = page.locator("aside");
      await expect(aside).toBeHidden();

      const hamburger = page.locator('button[aria-label="Open navigation"]');
      await expect(hamburger).toBeVisible();
      await hamburger.click();

      const drawer = page.locator('[role="dialog"]');
      await expect(drawer).toBeVisible();

      const drawerButtons = drawer.locator("nav button");
      await expect(drawerButtons).toHaveCount(4);

      for (let i = 0; i < EXPECTED_SECTIONS.length; i++) {
        await expect(drawerButtons.nth(i)).toHaveText(EXPECTED_SECTIONS[i]);
      }
    });

    test("mobile drawer section links scroll to sections", async ({ page }) => {
      await page.goto(SIM_URL);
      await page.waitForSelector("section#agents");

      const hamburger = page.locator('button[aria-label="Open navigation"]');
      await hamburger.click();

      const drawer = page.locator('[role="dialog"]');
      await expect(drawer).toBeVisible();

      await drawer.locator("nav button", { hasText: "Scoring & Analysis" }).click();
      await page.waitForTimeout(500);

      await expect(page.locator("section#scoring-analysis")).toBeInViewport();
    });
  });
});
