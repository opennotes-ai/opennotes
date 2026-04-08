import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { LoginPage, NavigationPage, PostPage, AdminPage, DiscourseAPI } from "../helpers";
import { REVIEWER1 } from "../fixtures/users";

function getApiKey(): string {
  if (process.env.DISCOURSE_API_KEY) return process.env.DISCOURSE_API_KEY;
  const paths = [
    resolve(dirname(fileURLToPath(import.meta.url)), "../../../docker/.discourse-api-key"),
    resolve(process.cwd(), "../docker/.discourse-api-key"),
    resolve(process.cwd(), "docker/.discourse-api-key"),
  ];
  for (const p of paths) {
    try { return readFileSync(p, "utf-8").trim(); } catch {}
  }
  return "";
}

const API_KEY = getApiKey();
const API_URL = process.env.DISCOURSE_API_URL || "http://localhost:3000";

test.describe("Discourse smoke tests", () => {
  test("can login as admin", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();
    expect(await login.isLoggedIn()).toBe(true);
  });

  test("can login as reviewer", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);
    expect(await login.isLoggedIn()).toBe(true);
  });

  test("can view an existing topic", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsReviewer();
    await page.goto("/t/welcome-to-discourse/5", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    const content = await page.textContent("body");
    expect(content).toContain("Welcome");
  });

  test("admin can see plugin page", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();
    await page.goto("/admin/plugins/discourse-opennotes", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    const text = await page.textContent("body");
    expect(text).toContain("OpenNotes");
  });

  test("admin can view plugin settings", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();
    await page.goto("/admin/site_settings?filter=opennotes", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    const text = await page.textContent("body");
    expect(text).toContain("server");
  });

  test("admin dashboard route resolves without routing error", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();
    await page.goto("/admin/plugins/discourse-opennotes/dashboard", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    const text = await page.textContent("body");
    expect(text).not.toContain("No route matches");
    expect(text).not.toContain("Routing Error");
    const dashboardOrPlugin = await page
      .locator(".opennotes-admin-dashboard, .admin-plugin-outlet")
      .first()
      .isVisible()
      .catch(() => false);
    const hasOpennotesContent = text?.toLowerCase().includes("opennotes") ?? false;
    expect(dashboardOrPlugin || hasOpennotesContent).toBe(true);
  });

  test("reviewer can navigate to categories", async ({ page }) => {
    const login = new LoginPage(page);
    const nav = new NavigationPage(page);
    await login.loginAsReviewer();
    await nav.goToLatest();
    expect(await nav.getCurrentPath()).toContain("latest");
  });
});
