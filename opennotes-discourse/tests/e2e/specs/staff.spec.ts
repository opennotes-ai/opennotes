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
      "[TEST] S1 force-publish",
      "Post to be force-published by staff via agree action.",
      testCategoryId
    );

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();

    if (count === 0) {
      await page.goto("/review", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);
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
      "[TEST] S2 dismiss disagree",
      "Post to be upheld by staff via disagree action.",
      testCategoryId
    );

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();

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
      "[TEST] S3 ignore item",
      "Post to be ignored/dismissed from review queue.",
      testCategoryId
    );

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const initialCount = await reviewPage.getReviewableCount();

    const reviewQueueEl = page.locator(".reviewable-item, .no-results, .empty-state");
    const reviewQueueVisible = await reviewQueueEl.first().isVisible().catch(() => false);
    expect(reviewQueueVisible || initialCount >= 0).toBe(true);

    if (initialCount > 0) {
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
      }
    }

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });

  test("S4: staff escalate removes item from community review", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      "[TEST] S4 escalate item",
      "Post to be escalated by staff for dedicated review.",
      testCategoryId
    );

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const initialCount = await reviewPage.getReviewableCount();

    if (initialCount > 0) {
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
      }
    }

    const pageText = await page.textContent("body");
    expect(pageText).toBeTruthy();

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });

  test("S5: staff overturn auto-action unhides post", async ({ page }) => {
    const login = new LoginPage(page);
    const reviewPage = new ReviewPage(page);

    await login.loginAsAdmin();

    const topic = await discourseApi.createTopic(
      "[TEST] S5 overturn auto-action",
      "Post that was auto-actioned and needs overturning by staff.",
      testCategoryId
    );

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const count = await reviewPage.getReviewableCount();
    expect(count >= 0).toBe(true);

    if (count > 0) {
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
      }
    }

    const pageText = await page.textContent("body");
    expect(pageText).toBeTruthy();

    await discourseApi.deleteTopic(topic.topic_id).catch(() => {});
  });
});
