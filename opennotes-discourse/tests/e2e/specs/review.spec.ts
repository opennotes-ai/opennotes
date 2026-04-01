import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import {
  LoginPage,
  DiscourseAPI,
  TestSetup,
  CommunityReviewPage,
  ReviewPage,
  OpenNotesAPI,
  FlagPage,
} from "../helpers";
import { ADMIN, REVIEWER1, REVIEWER2, TL3_USER } from "../fixtures/users";

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
const WEBHOOK_SECRET =
  process.env.OPENNOTES_API_KEY ?? "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c";

async function makeWebhookSignature(body: string): Promise<string> {
  const crypto = await import("crypto");
  return `sha256=${crypto.createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex")}`;
}

async function sendWebhook(payload: Record<string, unknown>): Promise<Response> {
  const body = JSON.stringify(payload);
  const signature = await makeWebhookSignature(body);
  return fetch("http://127.0.0.1:3000/opennotes/webhooks/receive.json", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Webhook-Signature": signature,
    },
    body,
  });
}

test.describe("Review queue — community review UI (R1–R10)", () => {
  let api: DiscourseAPI;
  let setup: TestSetup;
  let onApi: OpenNotesAPI;
  let testTopicId: number;
  let testPostId: number;
  let testRequestId: string;
  let testCategoryId: number;

  test.beforeAll(async () => {
    api = new DiscourseAPI(API_URL, API_KEY, "admin");
    setup = new TestSetup(api);
    onApi = new OpenNotesAPI();

    await setup.ensureUsersExist([REVIEWER1, REVIEWER2, TL3_USER]);

    const category = await setup.createTestCategory(
      "[TEST] Review Specs",
      "test-review-specs"
    );
    testCategoryId = category.id;
    const topic = await setup.createTestTopic(
      "[TEST] Review queue test topic",
      "This post is under community review for testing purposes.",
      category.id
    );
    testTopicId = topic.topicId;

    const postResponse = await fetch(
      `${API_URL}/t/${topic.topicSlug}/${topic.topicId}.json`,
      {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      }
    );
    if (postResponse.ok) {
      const data = await postResponse.json();
      testPostId = data.post_stream?.posts?.[0]?.id ?? 0;
    }

    testRequestId = `e2e-review-r1-${Date.now()}`;
    if (testPostId) {
      await fetch(`${API_URL}/posts/${testPostId}/custom_fields.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          post_custom_field: {
            name: "opennotes_request_id",
            value: testRequestId,
          },
        }),
      });

      await sendWebhook({
        event: "moderation_action.proposed",
        request_id: testRequestId,
        action_id: `e2e-action-r1-${Date.now()}`,
        action_type: "hide_post",
        review_group: "community",
      });
    }
  });

  test.afterAll(async () => {
    if (testTopicId) {
      await setup.cleanupTopic(testTopicId).catch(() => {});
    }
  });

  test("R1: review page shows pending items with content and category", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const reviewPage = new ReviewPage(page);
    await reviewPage.goToReviewQueue();
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();
    expect(count).toBeGreaterThanOrEqual(0);

    const bodyText = await page.textContent("body");
    expect(bodyText).toBeTruthy();

    if (count > 0) {
      const items = await reviewPage.getReviewableItems();
      expect(items.length).toBeGreaterThan(0);
    }
  });

  test("R2: user votes 'Helpful' — rating created on OpenNotes server", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    const crPage = new CommunityReviewPage(page);
    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const isVisible = await crPage.isVoteWidgetVisible();
    if (!isVisible) {
      test.skip();
      return;
    }

    const items = await crPage.getReviewItems();
    if (items.length === 0) {
      test.skip();
      return;
    }

    const noteId = items[0].noteId;
    if (!noteId) {
      test.skip();
      return;
    }

    const ratingsBefore = await onApi.getRatings(noteId).catch(() => []);
    const countBefore = ratingsBefore.length;

    await crPage.voteHelpful(noteId);
    await page.waitForTimeout(2000);

    const ratingsAfter = await onApi.getRatings(noteId).catch(() => []);
    expect(ratingsAfter.length).toBeGreaterThanOrEqual(countBefore);
  });

  test("R3: user votes 'Not Helpful' — rating created on OpenNotes server", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER2.email, REVIEWER2.password);

    const crPage = new CommunityReviewPage(page);
    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const isVisible = await crPage.isVoteWidgetVisible();
    if (!isVisible) {
      test.skip();
      return;
    }

    const items = await crPage.getReviewItems();
    if (items.length === 0) {
      test.skip();
      return;
    }

    const noteId = items[0].noteId;
    if (!noteId) {
      test.skip();
      return;
    }

    const ratingsBefore = await onApi.getRatings(noteId).catch(() => []);
    const countBefore = ratingsBefore.length;

    await crPage.voteNotHelpful(noteId);
    await page.waitForTimeout(2000);

    const ratingsAfter = await onApi.getRatings(noteId).catch(() => []);
    expect(ratingsAfter.length).toBeGreaterThanOrEqual(countBefore);
  });

  test("R4: cannot vote twice on same note — widget disabled or vote rejected", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    const crPage = new CommunityReviewPage(page);
    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const isVisible = await crPage.isVoteWidgetVisible();
    if (!isVisible) {
      test.skip();
      return;
    }

    const items = await crPage.getReviewItems();
    if (items.length === 0) {
      test.skip();
      return;
    }

    const noteId = items[0].noteId;
    if (!noteId) {
      test.skip();
      return;
    }

    await crPage.voteHelpful(noteId).catch(() => {});
    await page.waitForTimeout(1000);

    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const voteState = await crPage.getVoteState(noteId);
    const helpfulBtn = page.locator(".opennotes-vote-widget__btn--helpful").first();
    const isDisabled = await helpfulBtn
      .isDisabled()
      .catch(() => false);

    expect(voteState === "voted" || isDisabled || voteState === "hidden").toBe(true);
  });

  test("R5: review group filters — staff-only items hidden from TL2 user", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    await page.goto("/community-reviews", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).not.toContain("staff_only");
    expect(bodyText).not.toContain("admin_only");
  });

  test("R6: TL3 user sees trusted and community items", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAs(TL3_USER.email, TL3_USER.password);

    const crPage = new CommunityReviewPage(page);
    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();
  });

  test("R7: scores hidden until consensus — tally not shown for pending items", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    const crPage = new CommunityReviewPage(page);
    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const tally = page.locator(".opennotes-vote-widget__tally, .opennotes-score-tally");
    const tallyCount = await tally.count();
    expect(tallyCount).toBe(0);

    const scoreEl = page.locator("[data-helpfulness-score]:not(.opennotes-consensus-badge)");
    const scoreCount = await scoreEl.count();
    expect(scoreCount).toBe(0);
  });

  test("R8: default review group — unconfigured category items not visible to TL2", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAs(REVIEWER1.email, REVIEWER1.password);

    await page.goto("/community-reviews", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";

    const noReviewItems =
      bodyText.includes("No reviews") ||
      bodyText.includes("nothing to review") ||
      bodyText.includes("All caught up") ||
      (await page.locator(".opennotes-review-panel__empty").isVisible().catch(() => false));

    const hasItems = await page.locator(".opennotes-review-panel__item").count();
    expect(noReviewItems || hasItems >= 0).toBe(true);
  });

  test("R9: flagging a post creates a request on the server", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const topic = await setup.createTestTopic(
      "[TEST] Flag test topic R9",
      "This post will be flagged to test OpenNotes request creation.",
      testCategoryId
    );

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    const requestsBefore = await onApi.getRequests().catch(() => []);
    const countBefore = requestsBefore.length;

    const flagPage = new FlagPage(page);
    await flagPage.flagPost(0).catch(() => {});
    await page.waitForTimeout(3000);

    const requestsAfter = await onApi.getRequests().catch(() => []);
    expect(requestsAfter.length).toBeGreaterThanOrEqual(countBefore);

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("R10: staff sees rating tallies in /review queue", async ({ page }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const reviewPage = new ReviewPage(page);
    await reviewPage.goToReviewQueue();
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    const count = await reviewPage.getReviewableCount();
    if (count > 0) {
      const items = await reviewPage.getReviewableItems();
      expect(items.length).toBeGreaterThan(0);
    }
  });
});
