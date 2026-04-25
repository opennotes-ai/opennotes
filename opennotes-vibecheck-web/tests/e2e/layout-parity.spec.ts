import { test, expect } from "@playwright/test";

test.describe("Landing-page layout parity", () => {
  test("URL input and Analyze button render at the same pixel height", async ({
    page,
  }) => {
    await page.goto("/");
    const input = page.locator("#vibecheck-url");
    const button = page.locator('button[type="submit"]');

    await expect(input).toBeVisible();
    await expect(button).toBeVisible();

    const inputBox = await input.boundingBox();
    const buttonBox = await button.boundingBox();

    expect(inputBox).not.toBeNull();
    expect(buttonBox).not.toBeNull();

    const diff = Math.abs((inputBox?.height ?? 0) - (buttonBox?.height ?? 0));
    expect(diff).toBeLessThanOrEqual(1);
  });
});
