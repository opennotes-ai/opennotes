import { test, expect } from "@playwright/test";
import { LoginPage, NavigationPage, PostPage, AdminPage } from "../helpers";
import { ADMIN, REVIEWER1 } from "../fixtures/users";

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

  test("can create and view a topic", async ({ page }) => {
    const login = new LoginPage(page);
    const post = new PostPage(page);
    await login.loginAsReviewer();
    const topicUrl = await post.createTopic(
      "[TEST] Smoke Test Post",
      "This post was created by the Playwright smoke test."
    );
    expect(topicUrl).toBeTruthy();
    await page.goto(topicUrl);
    expect(await post.getPostContent(0)).toContain("Playwright smoke test");
  });

  test("admin can see plugin in admin panel", async ({ page }) => {
    const login = new LoginPage(page);
    const admin = new AdminPage(page);
    await login.loginAsAdmin();
    await admin.goToPlugins();
    expect(await admin.isPluginInstalled("discourse-opennotes")).toBe(true);
  });

  test("admin can view plugin settings", async ({ page }) => {
    const login = new LoginPage(page);
    const admin = new AdminPage(page);
    await login.loginAsAdmin();
    await admin.goToPluginSettings("opennotes");
    const serverUrl = await admin.getSettingValue("opennotes_server_url");
    expect(serverUrl).toContain("host.docker.internal");
  });

  test("reviewer can navigate to categories", async ({ page }) => {
    const login = new LoginPage(page);
    const nav = new NavigationPage(page);
    await login.loginAsReviewer();
    await nav.goToLatest();
    expect(await nav.getCurrentPath()).toContain("latest");
  });
});
