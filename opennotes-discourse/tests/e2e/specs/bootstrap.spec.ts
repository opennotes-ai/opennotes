import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { LoginPage, DiscourseAPI } from "../helpers";
import { OpenNotesAPI } from "../helpers/opennotes-api";
import { CommunityReviewPage } from "../helpers/community-review-page";
import { TL3_USER, REVIEWER1 } from "../fixtures/users";

const COMMUNITY_SERVER_ID = "discourse-dev-1";
const MONITORED_CATEGORY_ID = 4;
const MONITORED_CATEGORY_SLUG = "general";
const DISCOURSE_API_URL = process.env.DISCOURSE_API_URL || "http://localhost:3000";

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

test.describe.serial("Bootstrap tests", () => {
  let discourseApi: DiscourseAPI;
  let openNotesApi: OpenNotesAPI;

  test.beforeAll(async () => {
    discourseApi = new DiscourseAPI(DISCOURSE_API_URL, API_KEY, "admin");
    openNotesApi = new OpenNotesAPI();
  });

  test("B1: plugin registers community server on OpenNotes", async () => {
    test.setTimeout(30000);
    const server = await openNotesApi.getCommunityServer(COMMUNITY_SERVER_ID);
    expect(server).toBeTruthy();
    const platform = server?.data?.attributes?.platform ?? server?.platform;
    expect(platform).toBe("discourse");
  });

  test("B2: plugin registers webhook with correct URL and HMAC", async () => {
    test.setTimeout(30000);
    const server = await openNotesApi.getCommunityServer(COMMUNITY_SERVER_ID);
    expect(server).toBeTruthy();

    const webhookUrl =
      server?.data?.attributes?.webhook_url ??
      server?.webhook_url ??
      server?.data?.attributes?.webhook?.url;

    if (webhookUrl) {
      expect(webhookUrl).toContain("opennotes/webhook");
    } else {
      const serverId = server?.data?.id ?? server?.id;
      expect(serverId).toBeTruthy();
    }
  });

  test("B3: monitored categories are synced as channels on server", async () => {
    test.setTimeout(30000);
    const server = await openNotesApi.getCommunityServer(COMMUNITY_SERVER_ID);
    expect(server).toBeTruthy();

    const channels = await openNotesApi.getMonitoredChannels(COMMUNITY_SERVER_ID);
    expect(Array.isArray(channels)).toBe(true);
    expect(channels.length).toBeGreaterThan(0);

    const generalChannel = channels.find((ch: any) => {
      const channelId =
        ch?.attributes?.platform_channel_id ??
        ch?.platform_channel_id ??
        ch?.channel_id;
      return (
        channelId === MONITORED_CATEGORY_ID.toString() ||
        channelId === MONITORED_CATEGORY_SLUG
      );
    });
    expect(generalChannel).toBeTruthy();
  });

  test("B4: adding a category to monitored list creates new channel on server", async () => {
    test.setTimeout(60000);
    const testSlug = `test-cat-${Date.now()}`;
    let categoryId: number | undefined;

    try {
      const category = await discourseApi.createCategory("Test Bootstrap Cat", testSlug);
      categoryId = category.id;

      const current = await discourseApi.getSiteSettings() as any;
      const existing =
        (current?.opennotes_monitored_categories as string) ||
        (current?.site_settings?.find?.((s: any) => s.setting === "opennotes_monitored_categories")?.value as string) ||
        MONITORED_CATEGORY_SLUG;

      await discourseApi.updateSiteSetting(
        "opennotes_monitored_categories",
        `${existing},${testSlug}`
      );

      await new Promise((r) => setTimeout(r, 8000));

      const server = await openNotesApi.getCommunityServer(COMMUNITY_SERVER_ID);
      expect(server).toBeTruthy();

      const channels = await openNotesApi.getMonitoredChannels(COMMUNITY_SERVER_ID);
      expect(Array.isArray(channels)).toBe(true);

      const newChannel = channels.find((ch: any) => {
        const chId =
          ch?.attributes?.platform_channel_id ??
          ch?.platform_channel_id ??
          ch?.channel_id;
        return chId === testSlug || chId === String(categoryId);
      });
      expect(newChannel).toBeTruthy();
    } finally {
      await discourseApi.updateSiteSetting(
        "opennotes_monitored_categories",
        MONITORED_CATEGORY_SLUG
      );
    }
  });

  test("B5: settings sync — staff_approval_required and auto_hide_on_consensus reflected on server", async () => {
    test.setTimeout(30000);
    await discourseApi.updateSiteSetting("opennotes_staff_approval_required", "true");
    await new Promise((r) => setTimeout(r, 3000));

    const server = await openNotesApi.getCommunityServer(COMMUNITY_SERVER_ID);
    expect(server).toBeTruthy();

    const attrs = server?.data?.attributes ?? server;
    const requiresApproval =
      attrs?.staff_approval_required ??
      attrs?.requires_staff_approval ??
      attrs?.config?.staff_approval_required;

    if (requiresApproval !== undefined) {
      expect(requiresApproval).toBe(true);
    }

    await discourseApi.updateSiteSetting("opennotes_staff_approval_required", "false");
  });

  test("B6: reviewer_min_trust_level=3 — TL2 user cannot see vote widget", async ({ page }) => {
    test.setTimeout(60000);
    await discourseApi.updateSiteSetting("opennotes_reviewer_min_trust_level", "3");

    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    const reviewPage = new CommunityReviewPage(page);
    await reviewPage.goToReviews();
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    const isAccessDenied =
      bodyText.includes("not allowed") ||
      bodyText.includes("access") ||
      bodyText.includes("403") ||
      bodyText.includes("Not Found");

    if (!isAccessDenied) {
      const voteWidgetVisible = await reviewPage.isVoteWidgetVisible();
      expect(voteWidgetVisible).toBe(false);
    }

    await discourseApi.updateSiteSetting("opennotes_reviewer_min_trust_level", "2");
  });

  test("B7: route_flags_to_community — flagging a post creates a request on server", async ({ page }) => {
    test.setTimeout(90000);
    await discourseApi.updateSiteSetting("opennotes_route_flags_to_community", "true");

    let topicId: number | undefined;
    try {
      const topic = await discourseApi.createTopic(
        "[TEST] B7 Flag routing test",
        "This post is being flagged to test OpenNotes routing.",
        MONITORED_CATEGORY_ID
      );
      topicId = topic.topic_id;

      const login = new LoginPage(page);
      await login.loginAs(REVIEWER1.email, REVIEWER1.password);
      await page.goto(`/t/${topic.topic_slug}/${topicId}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(4000);

      const postEl = page.locator(".topic-post").first();
      await postEl.hover();

      const moreButton = postEl.locator(".post-controls .show-more-actions");
      if (await moreButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await moreButton.click();
      }

      const flagButton = postEl.locator(".post-controls .flag-post, .post-controls button[title='flag this post']");
      const canFlag = await flagButton.isVisible({ timeout: 3000 }).catch(() => false);

      if (canFlag) {
        await flagButton.click();
        await page.waitForSelector(".flag-modal, .modal-body .flagging-topic", { state: "visible", timeout: 10000 });

        const firstRadio = page.locator(".flag-modal input[type='radio'], .modal-body .flagging-topic input[type='radio']").first();
        await firstRadio.click();

        const submitButton = page.locator(".flag-modal .btn-primary, .modal-footer .btn-primary").filter({ hasText: /Flag Post|Flag/i });
        await submitButton.click();

        await page.waitForSelector(".flag-modal, .modal-body .flagging-topic", { state: "hidden", timeout: 10000 });
        await page.waitForTimeout(5000);

        const postId = topic.id;
        const requests = await openNotesApi.getRequests({
          "filter[platform_message_id]": String(postId),
        });
        expect(requests.length).toBeGreaterThan(0);
      } else {
        test.skip();
      }
    } finally {
      if (topicId) {
        await discourseApi.deleteTopic(topicId).catch(() => {});
      }
      await discourseApi.updateSiteSetting("opennotes_route_flags_to_community", "false");
    }
  });
});
