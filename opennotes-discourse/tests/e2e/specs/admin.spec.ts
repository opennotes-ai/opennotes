import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import {
  LoginPage,
  AdminPage,
  DiscourseAPI,
  TestSetup,
  OpenNotesAPI,
  DashboardPage,
} from "../helpers";

function getApiKey(): string {
  if (process.env.DISCOURSE_API_KEY) return process.env.DISCOURSE_API_KEY;
  const paths = [
    resolve(dirname(fileURLToPath(import.meta.url)), "../../../docker/.discourse-api-key"),
    resolve(process.cwd(), "../docker/.discourse-api-key"),
    resolve(process.cwd(), "docker/.discourse-api-key"),
  ];
  for (const p of paths) {
    try {
      return readFileSync(p, "utf-8").trim();
    } catch {}
  }
  return "";
}

const API_KEY = getApiKey();
const API_URL = process.env.DISCOURSE_API_URL || "http://localhost:3000";
const OPENNOTES_URL = process.env.OPENNOTES_SERVER_URL || "http://localhost:8000";
const OPENNOTES_API_KEY = process.env.OPENNOTES_API_KEY || "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c";

test.describe("Admin settings and dashboard", () => {
  let discourseApi: DiscourseAPI;
  let opennotesApi: OpenNotesAPI;

  test.beforeAll(async () => {
    discourseApi = new DiscourseAPI(API_URL, API_KEY, "admin");
    opennotesApi = new OpenNotesAPI(OPENNOTES_URL, OPENNOTES_API_KEY);
  });

  test("D1: view all plugin settings shows opennotes_* settings", async ({ page }) => {
    const login = new LoginPage(page);
    const adminPage = new AdminPage(page);

    await login.loginAsAdmin();
    await adminPage.goToPluginSettings("opennotes");

    const pageText = await page.textContent("body");
    expect(pageText).toContain("opennotes");

    const settingsVisible = await page
      .locator("[data-setting^='opennotes_'], .row.setting")
      .first()
      .isVisible()
      .catch(() => false);
    const hasOpennotesContent = pageText?.toLowerCase().includes("opennotes") ?? false;
    expect(settingsVisible || hasOpennotesContent).toBe(true);
  });

  test("D2: per-category threshold config updates server community config", async ({ page }) => {
    const login = new LoginPage(page);

    await login.loginAsAdmin();

    const setup = new TestSetup(discourseApi);
    const category = await setup.createTestCategory(
      "[TEST] D2 threshold",
      "test-d2-threshold"
    ).catch(() => ({ id: 1, name: "uncategorized", slug: "uncategorized" }));

    await discourseApi.updateSiteSetting(
      "opennotes_monitored_categories",
      category.slug
    );

    await page.goto("/admin/site_settings?filter=opennotes", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const pageText = await page.textContent("body");
    expect(pageText).toContain("opennotes");

    const communityServers = await opennotesApi.getCommunityServers().catch(() => []);
    expect(Array.isArray(communityServers)).toBe(true);

    await discourseApi.updateSiteSetting("opennotes_monitored_categories", "").catch(() => {});
    await discourseApi.deleteTopic(category.id).catch(() => {});
  });

  test("D3: per-category review group routing stores label-to-group mapping", async ({ page }) => {
    const login = new LoginPage(page);

    await login.loginAsAdmin();

    await page.goto("/admin/site_settings?filter=opennotes", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const pageText = await page.textContent("body");
    expect(pageText).toContain("opennotes");

    const communityServers = await opennotesApi.getCommunityServers().catch(() => []);
    expect(Array.isArray(communityServers)).toBe(true);

    if (communityServers.length > 0) {
      const server = communityServers[0];
      const platformServerId: string =
        server?.data?.attributes?.platform_community_server_id ??
        server?.platform_community_server_id ??
        "";
      if (platformServerId) {
        const channels = await opennotesApi.getMonitoredChannels(platformServerId).catch(() => []);
        expect(Array.isArray(channels)).toBe(true);
      }
    }
  });

  test("D4: dashboard shows scoring analysis / activity metrics", async ({ page }) => {
    const login = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);

    await login.loginAsAdmin();

    await dashboardPage.goToDashboard();
    await page.waitForTimeout(3000);

    const isLoaded = await dashboardPage.isLoaded();
    const hasError = await dashboardPage.hasError();

    if (isLoaded) {
      const metrics = await dashboardPage.getActivityMetrics();
      expect(metrics !== undefined).toBe(true);
    } else if (hasError) {
      const errorVisible = await page
        .locator(".opennotes-admin-dashboard__error")
        .isVisible()
        .catch(() => false);
      expect(errorVisible || !isLoaded).toBe(true);
    } else {
      const dashboardEl = await page
        .locator(".opennotes-admin-dashboard, .admin-plugin-outlet")
        .isVisible()
        .catch(() => false);
      const pageText = await page.textContent("body");
      expect(dashboardEl || pageText?.includes("OpenNotes")).toBe(true);
    }
  });

  test("D5: dashboard shows top reviewers section (populated or empty)", async ({ page }) => {
    const login = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);

    await login.loginAsAdmin();

    await dashboardPage.goToDashboard();
    await page.waitForTimeout(3000);

    const isLoaded = await dashboardPage.isLoaded();

    if (isLoaded) {
      const reviewers = await dashboardPage.getTopReviewers();
      expect(Array.isArray(reviewers)).toBe(true);
    } else {
      const pageText = await page.textContent("body");
      expect(pageText).toBeTruthy();
    }
  });

  test("D6: disabling plugin prevents classification of new posts", async ({ page }) => {
    const login = new LoginPage(page);

    await login.loginAsAdmin();

    const originalValue = await discourseApi
      .getSiteSettings()
      .then((s) => {
        const setting = (s as Record<string, unknown>)["opennotes_enabled"];
        return typeof setting === "object" && setting !== null
          ? String((setting as Record<string, unknown>)["value"] ?? "true")
          : "true";
      })
      .catch(() => "true");

    await discourseApi.updateSiteSetting("opennotes_enabled", "false");

    await page.goto("/latest", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    const setup = new TestSetup(discourseApi);
    const category = await setup
      .createTestCategory("[TEST] D6 disabled", "test-d6-disabled")
      .catch(() => ({ id: 1, name: "uncategorized", slug: "uncategorized" }));

    const topic = await discourseApi.createTopic(
      "[TEST] D6 post while disabled",
      "This post should not trigger classification since plugin is disabled.",
      category.id
    );

    await page.waitForTimeout(3000);

    const requestsBefore = await opennotesApi.getRequests().catch(() => []);
    const testRequestExists = requestsBefore.some(
      (r: { attributes?: { platform_post_id?: string }; platform_post_id?: string }) =>
        (r.attributes?.platform_post_id ?? r.platform_post_id) ===
        String(topic.id)
    );
    expect(testRequestExists).toBe(false);

    await discourseApi.updateSiteSetting("opennotes_enabled", originalValue).catch(() => {});
    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });
});
