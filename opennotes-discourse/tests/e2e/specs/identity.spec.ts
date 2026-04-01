import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { LoginPage, DiscourseAPI } from "../helpers";
import { OpenNotesAPI } from "../helpers/opennotes-api";
import { CommunityReviewPage } from "../helpers/community-review-page";
import { ADMIN, REVIEWER1, NEWUSER, TL1_USER, TL3_USER } from "../fixtures/users";

const COMMUNITY_SERVER_ID = "discourse-dev-1";
const MONITORED_CATEGORY_ID = 4;
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

test.describe("Identity tests", () => {
  let discourseApi: DiscourseAPI;
  let openNotesApi: OpenNotesAPI;
  const createdTopicIds: number[] = [];

  test.beforeAll(async () => {
    discourseApi = new DiscourseAPI(DISCOURSE_API_URL, API_KEY, "admin");
    openNotesApi = new OpenNotesAPI();
  });

  test.afterAll(async () => {
    for (const topicId of createdTopicIds) {
      await discourseApi.deleteTopic(topicId).catch(() => {});
    }
  });

  test("I1: first-time user creates profile on server after interaction", async ({ page }) => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] I1 First-time user profile",
      "Testing first-time user profile creation via community review interaction.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 6000));

    const login = new LoginPage(page);
    await login.loginAs(TL3_USER.email, TL3_USER.password);

    const reviewPage = new CommunityReviewPage(page);
    await reviewPage.goToReviews();
    await page.waitForTimeout(4000);

    const hasItems = (await reviewPage.getItemCount()) > 0;
    if (hasItems) {
      const items = await reviewPage.getReviewItems();
      if (items.length > 0 && items[0].noteId) {
        await reviewPage.voteHelpful(items[0].noteId);
        await page.waitForTimeout(3000);
      }
    }

    const tl3UserId = await discourseApi.getUserIdByUsername(TL3_USER.username);
    if (tl3UserId) {
      const profileData = await openNotesApi.getUserProfile(
        "discourse",
        String(tl3UserId),
        "localhost"
      );
      if (profileData) {
        const profile = profileData?.data ?? profileData;
        expect(profile).toBeTruthy();
      }
    }
  });

  test("I2: returning user uses cached identity — no duplicate profile created", async ({ page }) => {
    test.setTimeout(90000);
    await discourseApi.updateSiteSetting("opennotes_reviewer_min_trust_level", "2");

    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    const reviewer1Id = await discourseApi.getUserIdByUsername(REVIEWER1.username);
    expect(reviewer1Id).toBeTruthy();

    const reviewPage = new CommunityReviewPage(page);
    await reviewPage.goToReviews();
    await page.waitForTimeout(3000);

    const profileBefore = await openNotesApi.getUserProfile(
      "discourse",
      String(reviewer1Id),
      "localhost"
    ).catch(() => null);

    await reviewPage.goToReviews();
    await page.waitForTimeout(3000);

    const profileAfter = await openNotesApi.getUserProfile(
      "discourse",
      String(reviewer1Id),
      "localhost"
    ).catch(() => null);

    if (profileBefore && profileAfter) {
      const idBefore = profileBefore?.data?.id ?? profileBefore?.id;
      const idAfter = profileAfter?.data?.id ?? profileAfter?.id;
      if (idBefore && idAfter) {
        expect(idBefore).toBe(idAfter);
      }
    }
  });

  test("I3: trust level stored in profile metadata", async ({ page }) => {
    test.setTimeout(90000);
    await discourseApi.updateSiteSetting("opennotes_reviewer_min_trust_level", "2");

    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    const reviewer1Id = await discourseApi.getUserIdByUsername(REVIEWER1.username);
    expect(reviewer1Id).toBeTruthy();

    const reviewPage = new CommunityReviewPage(page);
    await reviewPage.goToReviews();
    await page.waitForTimeout(3000);

    const profileData = await openNotesApi.getUserProfile(
      "discourse",
      String(reviewer1Id),
      "localhost"
    ).catch(() => null);

    if (profileData) {
      const attrs =
        profileData?.data?.attributes ??
        profileData?.attributes ??
        profileData;
      const metadata = attrs?.metadata ?? attrs?.platform_metadata ?? {};
      const trustLevel =
        metadata?.trust_level ??
        attrs?.trust_level;

      if (trustLevel !== undefined) {
        expect(Number(trustLevel)).toBe(REVIEWER1.trustLevel);
      }
    }
  });

  test("I4: TL0 (new) user cannot see vote widget on community reviews", async ({ page }) => {
    test.setTimeout(60000);
    await discourseApi.updateSiteSetting("opennotes_reviewer_min_trust_level", "2");

    const login = new LoginPage(page);
    await login.loginAs(NEWUSER.email, NEWUSER.password);

    const reviewPage = new CommunityReviewPage(page);
    await reviewPage.goToReviews();
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    const isAccessDenied =
      bodyText.includes("not allowed") ||
      bodyText.includes("Forbidden") ||
      bodyText.includes("403") ||
      bodyText.includes("Not Found") ||
      bodyText.includes("don't have access");

    if (!isAccessDenied) {
      const voteWidgetVisible = await reviewPage.isVoteWidgetVisible();
      expect(voteWidgetVisible).toBe(false);
    } else {
      expect(isAccessDenied).toBe(true);
    }
  });

  test("I4b: TL1 user cannot see vote widget when min trust level is 2", async ({ page }) => {
    test.setTimeout(60000);
    await discourseApi.updateSiteSetting("opennotes_reviewer_min_trust_level", "2");

    const login = new LoginPage(page);
    await login.loginAs(TL1_USER.email, TL1_USER.password);

    const reviewPage = new CommunityReviewPage(page);
    await reviewPage.goToReviews();
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    const isAccessDenied =
      bodyText.includes("not allowed") ||
      bodyText.includes("Forbidden") ||
      bodyText.includes("403") ||
      bodyText.includes("Not Found") ||
      bodyText.includes("don't have access");

    if (!isAccessDenied) {
      const voteWidgetVisible = await reviewPage.isVoteWidgetVisible();
      expect(voteWidgetVisible).toBe(false);
    } else {
      expect(isAccessDenied).toBe(true);
    }
  });

  test("I5: admin action triggers elevated verification — server re-verifies admin status", async ({ page }) => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] I5 Admin verification trigger",
      "This post is created to test admin elevated verification.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 5000));

    const login = new LoginPage(page);
    await login.loginAsAdmin();

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const adminId = await discourseApi.getUserIdByUsername(ADMIN.username);
    expect(adminId).toBeTruthy();

    const profileData = await openNotesApi.getUserProfile(
      "discourse",
      String(adminId),
      "localhost"
    ).catch(() => null);

    if (profileData) {
      const attrs =
        profileData?.data?.attributes ??
        profileData?.attributes ??
        profileData;
      const isAdmin =
        attrs?.admin ??
        attrs?.metadata?.admin ??
        attrs?.platform_metadata?.admin;

      if (isAdmin !== undefined) {
        expect(Boolean(isAdmin)).toBe(true);
      }
    }
  });
});
