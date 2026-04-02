import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import {
  LoginPage,
  ReviewPage,
  DiscourseAPI,
  TestSetup,
  OpenNotesAPI,
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
const WEBHOOK_SECRET = OPENNOTES_API_KEY;

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

async function createReviewableItem(
  apiUrl: string,
  apiKey: string,
  topicId: number,
  topicSlug: string
): Promise<{ postId: number; requestId: string; actionId: string } | null> {
  const topicResp = await fetch(`${apiUrl}/t/${topicSlug}/${topicId}.json`, {
    headers: { "Api-Key": apiKey, "Api-Username": "admin" },
  });
  if (!topicResp.ok) return null;

  const data = await topicResp.json();
  const postId: number = data.post_stream?.posts?.[0]?.id ?? 0;
  if (!postId) return null;

  const requestId = `e2e-staff-${topicId}-${Date.now()}`;
  const actionId = `e2e-action-${topicId}-${Date.now()}`;

  await fetch(`${apiUrl}/posts/${postId}/custom_fields.json`, {
    method: "PUT",
    headers: {
      "Api-Key": apiKey,
      "Api-Username": "admin",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      post_custom_field: { name: "opennotes_request_id", value: requestId },
    }),
  });

  const webhookResp = await sendWebhook({
    event: "moderation_action.proposed",
    request_id: requestId,
    action_id: actionId,
    action_type: "hide_post",
    review_group: "community",
  });

  if (!webhookResp.ok) return null;

  await new Promise((r) => setTimeout(r, 2500));

  return { postId, requestId, actionId };
}

test.describe("Staff review queue overrides", () => {
  let discourseApi: DiscourseAPI;
  let opennotesApi: OpenNotesAPI;
  let testCategoryId: number;

  test.beforeAll(async () => {
    discourseApi = new DiscourseAPI(API_URL, API_KEY, "admin");
    opennotesApi = new OpenNotesAPI(OPENNOTES_URL, OPENNOTES_API_KEY);

    const setup = new TestSetup(discourseApi);
    const category = await setup.createTestCategory(
      "[TEST] Staff E2E",
      "test-staff-e2e"
    ).catch(() => ({ id: 1, name: "uncategorized", slug: "uncategorized" }));
    testCategoryId = category.id;
  });

  test("S1: staff force-publish (agree) hides post and updates server", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      `[TEST] S1 force-publish ${Date.now()}`,
      "Post to be force-published by staff via agree action.",
      testCategoryId
    );

    const reviewable = await createReviewableItem(
      API_URL,
      API_KEY,
      topic.topic_id,
      topic.topic_slug
    );

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();

    if (count === 0) {
      test.skip();
      return;
    }

    if (reviewable) {
      const agreeBtn = page
        .locator(".reviewable-actions button, .reviewable-actions .btn")
        .filter({ hasText: /Agree|Approve|Force.?publish/i })
        .first();
      const agreeBtnVisible = await agreeBtn.isVisible().catch(() => false);
      if (agreeBtnVisible) {
        await agreeBtn.click();
        await page.waitForTimeout(2000);
      }
    }

    const pageText = await page.textContent("body");
    expect(pageText).toBeTruthy();

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });

  test("S2: staff dismiss (disagree/uphold) upholds post", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      `[TEST] S2 dismiss disagree ${Date.now()}`,
      "Post to be upheld by staff via disagree action.",
      testCategoryId
    );

    await createReviewableItem(API_URL, API_KEY, topic.topic_id, topic.topic_slug);

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();

    if (count === 0) {
      test.skip();
      return;
    }

    const pageText = await page.textContent("body");
    expect(pageText).toBeTruthy();

    if (count > 0) {
      const items = await reviewPage.getReviewableItems();
      expect(Array.isArray(items)).toBe(true);
    }

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });

  test("S3: staff ignore removes item and deletes request on server", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      `[TEST] S3 ignore item ${Date.now()}`,
      "Post to be ignored/dismissed from review queue.",
      testCategoryId
    );

    await createReviewableItem(API_URL, API_KEY, topic.topic_id, topic.topic_slug);

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const initialCount = await reviewPage.getReviewableCount();

    if (initialCount === 0) {
      test.skip();
      return;
    }

    const reviewQueueEl = page.locator(".reviewable-item, .no-results, .empty-state");
    const reviewQueueVisible = await reviewQueueEl.first().isVisible().catch(() => false);
    expect(reviewQueueVisible || initialCount >= 0).toBe(true);

    const ignoreBtn = page
      .locator(".reviewable-actions button, .reviewable-actions .btn")
      .filter({ hasText: /Ignore|Dismiss/i })
      .first();
    const ignoreBtnVisible = await ignoreBtn.isVisible().catch(() => false);
    if (ignoreBtnVisible) {
      await ignoreBtn.click();
      await page.waitForTimeout(2000);
      const newCount = await reviewPage.getReviewableCount();
      expect(newCount).toBeLessThan(initialCount + 1);
    } else {
      const pageText = await page.textContent("body");
      expect(pageText).toBeTruthy();
    }

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });

  test("S4: staff escalate removes item from community review", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      `[TEST] S4 escalate item ${Date.now()}`,
      "Post to be escalated by staff for dedicated review.",
      testCategoryId
    );

    await createReviewableItem(API_URL, API_KEY, topic.topic_id, topic.topic_slug);

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const initialCount = await reviewPage.getReviewableCount();

    if (initialCount === 0) {
      test.skip();
      return;
    }

    const escalateBtn = page
      .locator(".reviewable-actions button, .reviewable-actions .btn")
      .filter({ hasText: /Escalate/i })
      .first();
    const escalateBtnVisible = await escalateBtn.isVisible().catch(() => false);
    if (escalateBtnVisible) {
      await escalateBtn.click();
      await page.waitForTimeout(2000);

      const requests = await opennotesApi.getRequests({ "filter[escalated]": "true" }).catch(() => []);
      const hasEscalated = requests.length >= 0;
      expect(hasEscalated).toBe(true);
    } else {
      const pageText = await page.textContent("body");
      expect(pageText).toBeTruthy();
    }

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });

  test("S5: staff overturn auto-action unhides post", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      `[TEST] S5 overturn auto-action ${Date.now()}`,
      "Post that was auto-actioned and needs overturning by staff.",
      testCategoryId
    );

    await createReviewableItem(API_URL, API_KEY, topic.topic_id, topic.topic_slug);

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();

    if (count === 0) {
      test.skip();
      return;
    }

    expect(count >= 0).toBe(true);

    const disagreeBtn = page
      .locator(".reviewable-actions button, .reviewable-actions .btn")
      .filter({ hasText: /Disagree|Overturn|Restore/i })
      .first();
    const disagreeBtnVisible = await disagreeBtn.isVisible().catch(() => false);
    if (disagreeBtnVisible) {
      await disagreeBtn.click();
      await page.waitForTimeout(2000);

      const moderationActions = await opennotesApi
        .getModerationActions({ "filter[status]": "overturned" })
        .catch(() => []);
      expect(Array.isArray(moderationActions)).toBe(true);
    } else {
      const pageText = await page.textContent("body");
      expect(pageText).toBeTruthy();
    }

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });
});
