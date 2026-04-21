import { test, expect, type Page } from "@playwright/test";

const DESKTOP = { width: 1280, height: 720 } as const;
const MOBILE = { width: 375, height: 812 } as const;

async function preparePage(page: Page) {
  await page.addStyleTag({
    content:
      "*, *::before, *::after { animation-duration: 0s !important; animation-delay: 0s !important; transition-duration: 0s !important; transition-delay: 0s !important; caret-color: transparent !important; }",
  });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  });
}

test.describe("Visual parity (post @opennotes/tokens + @opennotes/ui migration)", () => {
  test.describe("login page", () => {
    test.describe("desktop", () => {
      test.use({ viewport: DESKTOP });

      test("main content snapshot", async ({ page }) => {
        await page.goto("/login", { waitUntil: "networkidle" });
        await preparePage(page);
        await expect(page.locator("main")).toHaveScreenshot(
          "login-desktop-main.png",
        );
      });
    });

    test.describe("mobile", () => {
      test.use({ viewport: MOBILE });

      test("main content snapshot", async ({ page }) => {
        await page.goto("/login", { waitUntil: "networkidle" });
        await preparePage(page);
        await expect(page.locator("main")).toHaveScreenshot(
          "login-mobile-main.png",
        );
      });
    });
  });

  test.describe("register page", () => {
    test.describe("desktop", () => {
      test.use({ viewport: DESKTOP });

      test("main content snapshot", async ({ page }) => {
        await page.goto("/register", { waitUntil: "networkidle" });
        await preparePage(page);
        await expect(page.locator("main")).toHaveScreenshot(
          "register-desktop-main.png",
        );
      });
    });

    test.describe("mobile", () => {
      test.use({ viewport: MOBILE });

      test("main content snapshot", async ({ page }) => {
        await page.goto("/register", { waitUntil: "networkidle" });
        await preparePage(page);
        await expect(page.locator("main")).toHaveScreenshot(
          "register-mobile-main.png",
        );
      });
    });
  });
});
