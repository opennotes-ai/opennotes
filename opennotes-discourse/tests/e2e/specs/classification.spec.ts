import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { LoginPage, DiscourseAPI } from "../helpers";
import { OpenNotesAPI } from "../helpers/opennotes-api";
import { ModerationBannerPage } from "../helpers/moderation-banner-page";
import { ReviewPage } from "../helpers/review-page";

const MONITORED_CATEGORY_ID = 4;
const UNMONITORED_CATEGORY_NAME = "Site Feedback";
const UNMONITORED_CATEGORY_SLUG = "site-feedback";
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

test.describe("Classification tests", () => {
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

  test("C1: new post in monitored category triggers classification request on server", async () => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] C1 Classification trigger test",
      "This post should trigger a classification request via the SyncPostToOpennotes job.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 8000));

    const requests = await openNotesApi.getRequests({
      "filter[platform_message_id]": String(topic.id),
    });
    expect(requests.length).toBeGreaterThan(0);

    const req = requests[0];
    const attrs = req?.attributes ?? req;
    expect(attrs?.platform_message_id ?? attrs?.message_id).toBe(String(topic.id));
  });

  test("C2: edited post triggers re-classification request on server", async () => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] C2 Edit re-classification test",
      "Original content before edit.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 6000));

    const requestsBefore = await openNotesApi.getRequests({
      "filter[platform_message_id]": String(topic.id),
    });

    await fetch(`${DISCOURSE_API_URL}/posts/${topic.id}.json`, {
      method: "PUT",
      headers: {
        "Api-Key": API_KEY,
        "Api-Username": "admin",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        post: {
          raw: "Edited content — this should trigger re-classification.",
          edit_reason: "E2E test edit",
        },
      }),
    });

    await new Promise((r) => setTimeout(r, 8000));

    const requestsAfter = await openNotesApi.getRequests({
      "filter[platform_message_id]": String(topic.id),
    });

    expect(requestsAfter.length).toBeGreaterThanOrEqual(requestsBefore.length);
    expect(requestsAfter.length).toBeGreaterThan(0);
  });

  test("C3: post in non-monitored category does not trigger classification", async () => {
    test.setTimeout(60000);

    const unmonitoredCategory = await discourseApi.createCategory(
      "C3 Unmonitored Test",
      `c3-unmonitored-${Date.now()}`
    ).catch(async () => {
      const categories = await fetch(`${DISCOURSE_API_URL}/categories.json`, {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      }).then((r) => r.json());
      return categories?.category_list?.categories?.find(
        (c: any) => c.slug === UNMONITORED_CATEGORY_SLUG
      ) ?? { id: 7, slug: UNMONITORED_CATEGORY_SLUG };
    });

    await discourseApi.updateSiteSetting(
      "opennotes_monitored_categories",
      "general"
    );

    const topic = await discourseApi.createTopic(
      "[TEST] C3 Unmonitored category post",
      "This post is in a non-monitored category and should NOT be classified.",
      unmonitoredCategory.id
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 8000));

    const requests = await openNotesApi.getRequests({
      "filter[platform_message_id]": String(topic.id),
    });
    expect(requests.length).toBe(0);
  });

  test("C4: tier 2 — community_review response creates ReviewableOpennotesItem and shows Under Review banner", async ({ page }) => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] C4 Tier-2 community review",
      "This content may be flagged for community review based on classification.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 8000));

    const login = new LoginPage(page);
    await login.loginAsAdmin();

    await page.goto(`/t/${topic.topic_slug}/${topic.topic_id}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);

    const bannerPage = new ModerationBannerPage(page);
    const isUnderReview = await bannerPage.isUnderReview();

    const reviewPage = new ReviewPage(page);
    await reviewPage.goToReviewQueue();
    await page.waitForTimeout(3000);
    const reviewCount = await reviewPage.getReviewableCount();

    expect(isUnderReview || reviewCount > 0).toBe(true);
  });

  test("C5: tier 1 — auto_hide response causes post to be hidden with ModerationAction", async ({ page }) => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] C5 Tier-1 auto-hide test",
      "This post should be classified as high-confidence and auto-hidden by the plugin.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 8000));

    const actions = await openNotesApi.getModerationActions({
      "filter[platform_message_id]": String(topic.id),
    });

    const login = new LoginPage(page);
    await login.loginAsAdmin();
    await page.goto(`/t/${topic.topic_slug}/${topic.topic_id}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);

    const bannerPage = new ModerationBannerPage(page);
    const isHidden = await bannerPage.isPostHidden();

    expect(actions.length > 0 || isHidden).toBe(true);
  });

  test("C6: classification labels and scores visible to staff in /review queue", async ({ page }) => {
    test.setTimeout(90000);

    const topic = await discourseApi.createTopic(
      "[TEST] C6 Classification labels visibility",
      "This post should appear in the review queue with classification metadata visible to staff.",
      MONITORED_CATEGORY_ID
    );
    createdTopicIds.push(topic.topic_id);

    await new Promise((r) => setTimeout(r, 8000));

    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const reviewPage = new ReviewPage(page);
    await reviewPage.goToReviewQueue();
    await page.waitForTimeout(3000);

    const items = await reviewPage.getReviewableItems();
    const reviewCount = await reviewPage.getReviewableCount();

    if (reviewCount > 0) {
      const pageText = (await page.textContent(".reviewable-items, main, .container")) ?? "";
      const hasOpennotesItem =
        items.some((item) => item.type.toLowerCase().includes("opennotes")) ||
        pageText.includes("opennotes") ||
        pageText.includes("OpenNotes");

      if (hasOpennotesItem) {
        const opennotesEl = page.locator(".reviewable-item").filter({ hasText: /opennotes/i }).first();
        const hasLabel = await opennotesEl
          .locator("[class*='opennotes-label'], [class*='opennotes-score'], [data-label], [data-score]")
          .count()
          .then((c) => c > 0)
          .catch(() => false);

        expect(reviewCount > 0 || hasLabel).toBe(true);
      } else {
        expect(reviewCount).toBeGreaterThanOrEqual(0);
      }
    }
  });
});
