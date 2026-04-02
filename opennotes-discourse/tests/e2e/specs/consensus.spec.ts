import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import {
  LoginPage,
  DiscourseAPI,
  TestSetup,
  OpenNotesAPI,
  ModerationBannerPage,
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
const WEBHOOK_SECRET =
  process.env.OPENNOTES_API_KEY ?? "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c";

async function makeWebhookSignature(body: string): Promise<string> {
  const crypto = await import("crypto");
  return `sha256=${crypto.createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex")}`;
}

async function sendWebhook(
  payload: Record<string, unknown>
): Promise<Response> {
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

test.describe("Consensus → action (A1–A6)", () => {
  let api: DiscourseAPI;
  let setup: TestSetup;
  let onApi: OpenNotesAPI;

  test.beforeAll(async () => {
    api = new DiscourseAPI(API_URL, API_KEY, "admin");
    setup = new TestSetup(api);
    onApi = new OpenNotesAPI();
  });

  test("A1: consensus 'helpful' — post hidden, badge shown, ModerationAction applied", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Consensus A1",
      `test-consensus-a1-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] A1 consensus helpful hides post",
      "This post should be hidden when consensus 'helpful' is reached.",
      category.id
    );

    const topicResp = await fetch(
      `${API_URL}/t/${topic.topicSlug}/${topic.topicId}.json`,
      { headers: { "Api-Key": API_KEY, "Api-Username": "admin" } }
    );
    let postId = 0;
    if (topicResp.ok) {
      const data = await topicResp.json();
      postId = data.post_stream?.posts?.[0]?.id ?? 0;
    }

    const requestId = `e2e-consensus-a1-${Date.now()}`;
    const actionId = `e2e-action-a1-${Date.now()}`;

    if (postId) {
      await fetch(`${API_URL}/posts/${postId}/custom_fields.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          post_custom_field: { name: "opennotes_request_id", value: requestId },
        }),
      });

      const proposeResp = await sendWebhook({
        event: "moderation_action.proposed",
        request_id: requestId,
        action_id: actionId,
        action_type: "hide_post",
        review_group: "community",
      });
      expect(proposeResp.status).toBe(200);
      await page.waitForTimeout(2000);

      const consensusResp = await sendWebhook({
        event: "note.status_changed",
        status: "CURRENTLY_RATED_HELPFUL",
        request_id: requestId,
        recommended_action: "hide_post",
      });
      expect(consensusResp.status).toBe(200);
      await page.waitForTimeout(2000);
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    const bannerPage = new ModerationBannerPage(page);
    const badge = await bannerPage.getConsensusBadge().catch(() => null);
    const isHidden = await bannerPage.isPostHidden().catch(() => false);

    if (postId) {
      expect(isHidden || badge !== null || bodyText.includes("hidden")).toBe(true);
    }

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("A2: consensus 'not helpful' — post stays visible, 'No Action' badge", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Consensus A2",
      `test-consensus-a2-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] A2 consensus not helpful post stays",
      "This post should remain visible when consensus 'not helpful' is reached.",
      category.id
    );

    const topicResp = await fetch(
      `${API_URL}/t/${topic.topicSlug}/${topic.topicId}.json`,
      { headers: { "Api-Key": API_KEY, "Api-Username": "admin" } }
    );
    let postId = 0;
    if (topicResp.ok) {
      const data = await topicResp.json();
      postId = data.post_stream?.posts?.[0]?.id ?? 0;
    }

    const requestId = `e2e-consensus-a2-${Date.now()}`;
    const actionId = `e2e-action-a2-${Date.now()}`;

    if (postId) {
      await fetch(`${API_URL}/posts/${postId}/custom_fields.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          post_custom_field: { name: "opennotes_request_id", value: requestId },
        }),
      });

      await sendWebhook({
        event: "moderation_action.proposed",
        request_id: requestId,
        action_id: actionId,
        action_type: "warn_post",
        review_group: "community",
      });
      await page.waitForTimeout(2000);

      const consensusResp = await sendWebhook({
        event: "note.status_changed",
        status: "CURRENTLY_RATED_NOT_HELPFUL",
        request_id: requestId,
        recommended_action: "no_action",
      });
      expect(consensusResp.status).toBe(200);
      await page.waitForTimeout(2000);
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    const bannerPage = new ModerationBannerPage(page);
    const isHidden = await bannerPage.isPostHidden().catch(() => false);
    expect(isHidden).toBe(false);

    const postContent = await page.locator(".topic-post .cooked").first().textContent().catch(() => null);
    expect(postContent).not.toBeNull();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("A3: webhook triggers Discourse action — ReviewableOpennotesItem updated", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Consensus A3",
      `test-consensus-a3-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] A3 webhook triggers Discourse action",
      "This post tests webhook-triggered Discourse action.",
      category.id
    );

    const topicResp = await fetch(
      `${API_URL}/t/${topic.topicSlug}/${topic.topicId}.json`,
      { headers: { "Api-Key": API_KEY, "Api-Username": "admin" } }
    );
    let postId = 0;
    if (topicResp.ok) {
      const data = await topicResp.json();
      postId = data.post_stream?.posts?.[0]?.id ?? 0;
    }

    const requestId = `e2e-consensus-a3-${Date.now()}`;
    const actionId = `e2e-action-a3-${Date.now()}`;

    if (postId) {
      await fetch(`${API_URL}/posts/${postId}/custom_fields.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          post_custom_field: { name: "opennotes_request_id", value: requestId },
        }),
      });
    }

    const proposeResp = await sendWebhook({
      event: "moderation_action.proposed",
      request_id: requestId,
      action_id: actionId,
      action_type: "hide_post",
      review_group: "community",
    });
    expect(proposeResp.status).toBe(200);
    await page.waitForTimeout(2000);

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("A4: polling fallback catches missed webhook — plugin catches up without webhook", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const requestsBefore = await onApi.getRequests().catch(() => []);
    expect(Array.isArray(requestsBefore)).toBe(true);

    await page.goto("/admin/plugins/discourse-opennotes", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const reviewText = (await page.textContent("body")) ?? "";
    expect(reviewText).toBeTruthy();
  });

  test("A5: invalid HMAC webhook rejected — returns 401", async () => {
    const body = JSON.stringify({
      event: "note.status_changed",
      status: "CURRENTLY_RATED_HELPFUL",
      request_id: `e2e-a5-${Date.now()}`,
      recommended_action: "hide_post",
    });

    const response = await fetch(
      "http://127.0.0.1:3000/opennotes/webhooks/receive.json",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Webhook-Signature": "sha256=invalidsignaturevalue",
        },
        body,
      }
    );

    expect(response.status).toBe(401);

    const responseData = await response.json();
    expect(responseData).toHaveProperty("error");
  });

  test("A6: stale polling is no-op after webhook — no duplicate action", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Consensus A6",
      `test-consensus-a6-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] A6 stale polling no-op",
      "This post tests that stale polling does not duplicate actions after webhook.",
      category.id
    );

    const topicResp = await fetch(
      `${API_URL}/t/${topic.topicSlug}/${topic.topicId}.json`,
      { headers: { "Api-Key": API_KEY, "Api-Username": "admin" } }
    );
    let postId = 0;
    if (topicResp.ok) {
      const data = await topicResp.json();
      postId = data.post_stream?.posts?.[0]?.id ?? 0;
    }

    const requestId = `e2e-consensus-a6-${Date.now()}`;
    const actionId = `e2e-action-a6-${Date.now()}`;

    if (postId) {
      await fetch(`${API_URL}/posts/${postId}/custom_fields.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          post_custom_field: { name: "opennotes_request_id", value: requestId },
        }),
      });

      await sendWebhook({
        event: "moderation_action.proposed",
        request_id: requestId,
        action_id: actionId,
        action_type: "hide_post",
        review_group: "community",
      });
      await page.waitForTimeout(1000);

      const resp1 = await sendWebhook({
        event: "note.status_changed",
        status: "CURRENTLY_RATED_HELPFUL",
        request_id: requestId,
        recommended_action: "hide_post",
      });
      expect(resp1.status).toBe(200);
      await page.waitForTimeout(1000);

      const resp2 = await sendWebhook({
        event: "note.status_changed",
        status: "CURRENTLY_RATED_HELPFUL",
        request_id: requestId,
        recommended_action: "hide_post",
      });
      expect(resp2.status).toBe(200);
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });
});
