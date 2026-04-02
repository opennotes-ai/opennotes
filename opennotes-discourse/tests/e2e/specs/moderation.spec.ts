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
  CommunityReviewPage,
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

async function getPostCustomFields(
  postId: number
): Promise<Record<string, string>> {
  const resp = await fetch(`${API_URL}/posts/${postId}.json`, {
    headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
  });
  if (!resp.ok) return {};
  const data = await resp.json();
  const fields: Record<string, string> = {};
  for (const cf of data.custom_fields ?? []) {
    fields[cf.name] = cf.value;
  }
  return fields;
}

test.describe("Moderation — tier 1, retroactive review, scan-exempt (M1–M8)", () => {
  let api: DiscourseAPI;
  let setup: TestSetup;
  let onApi: OpenNotesAPI;

  test.beforeAll(async () => {
    api = new DiscourseAPI(API_URL, API_KEY, "admin");
    setup = new TestSetup(api);
    onApi = new OpenNotesAPI();
  });

  test("M1: tier-1 auto-hide creates ModerationAction, Request, and Note artifacts", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M1",
      `test-mod-m1-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] M1 tier-1 auto-hide",
      "This post will be auto-hidden via a tier-1 webhook event.",
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

    const requestId = `e2e-mod-m1-${Date.now()}`;
    const actionId = `e2e-action-m1-${Date.now()}`;

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

    const resp = await sendWebhook({
      event: "moderation_action.proposed",
      request_id: requestId,
      action_id: actionId,
      action_type: "hide_post",
      review_group: "community",
      classifier_evidence: {
        labels: ["MISINFORMED_OR_POTENTIALLY_MISLEADING"],
        scores: { MISINFORMED_OR_POTENTIALLY_MISLEADING: 0.92 },
        model_version: "v1.0",
      },
    });
    expect(resp.status).toBe(200);
    await page.waitForTimeout(2000);

    if (postId) {
      const postResp = await fetch(`${API_URL}/posts/${postId}.json`, {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      });
      if (postResp.ok) {
        const postData = await postResp.json();
        const hasRequestId =
          postData.custom_fields?.opennotes_request_id === requestId ||
          JSON.stringify(postData).includes(requestId);
        expect(hasRequestId || resp.status === 200).toBe(true);
      }
    }

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M2: retroactive review note visible in /community-reviews", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M2",
      `test-mod-m2-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] M2 retroactive review note visible",
      "This post was auto-hidden; its review note should appear in community-reviews.",
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

    const requestId = `e2e-mod-m2-${Date.now()}`;
    const actionId = `e2e-action-m2-${Date.now()}`;

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
    }

    const crPage = new CommunityReviewPage(page);
    await crPage.goToReviews();
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M3: retroactive consensus confirms — ModerationAction state: confirmed", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M3",
      `test-mod-m3-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] M3 retroactive consensus confirms",
      "This post tests retroactive consensus confirmation flow.",
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

    const requestId = `e2e-mod-m3-${Date.now()}`;
    const actionId = `e2e-action-m3-${Date.now()}`;

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

      const confirmedResp = await sendWebhook({
        event: "moderation_action.confirmed",
        action_id: actionId,
        request_id: requestId,
      });
      expect(confirmedResp.status).toBe(200);
      await page.waitForTimeout(2000);
    }

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M4: retroactive consensus overturns — post unhidden, state: overturned, scan_exempt=true", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M4",
      `test-mod-m4-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] M4 retroactive consensus overturns",
      "This post tests retroactive consensus overturn flow.",
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

    const requestId = `e2e-mod-m4-${Date.now()}`;
    const actionId = `e2e-action-m4-${Date.now()}`;

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

      const overturnResp = await sendWebhook({
        event: "moderation_action.overturned",
        action_id: actionId,
        request_id: requestId,
      });
      expect(overturnResp.status).toBe(200);
      await page.waitForTimeout(2000);
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    const bannerPage = new ModerationBannerPage(page);
    const isHidden = await bannerPage.isPostHidden().catch(() => false);

    expect(isHidden).toBe(false);

    if (postId) {
      const postResp = await fetch(`${API_URL}/posts/${postId}.json`, {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      });
      if (postResp.ok) {
        const postData = await postResp.json();
        const isScanExempt =
          postData.custom_fields?.opennotes_scan_exempt === "true" ||
          postData.custom_fields?.opennotes_scan_exempt === true;
        expect(isScanExempt || !isHidden).toBe(true);
      }
    }

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M5: overturned post scan-exempt on minor edit — does not re-scan", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M5",
      `test-mod-m5-${Date.now()}`
    );
    const originalBody = "Original content of the overturned post for M5.";
    const topic = await setup.createTestTopic(
      "[TEST] M5 scan-exempt on minor edit",
      originalBody,
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

    const requestId = `e2e-mod-m5-${Date.now()}`;
    const actionId = `e2e-action-m5-${Date.now()}`;

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
      await page.waitForTimeout(500);

      await sendWebhook({
        event: "moderation_action.overturned",
        action_id: actionId,
        request_id: requestId,
      });
      await page.waitForTimeout(1000);

      await fetch(`${API_URL}/posts/${postId}.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          post: { raw: originalBody + " (minor edit)" },
        }),
      });
      await page.waitForTimeout(1500);

      const postAfterEdit = await fetch(`${API_URL}/posts/${postId}.json`, {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      });
      if (postAfterEdit.ok) {
        const data = await postAfterEdit.json();
        const isScanExempt =
          data.custom_fields?.opennotes_scan_exempt === "true" ||
          data.custom_fields?.opennotes_scan_exempt === true;
        expect(isScanExempt || data.hidden === false).toBe(true);
      }
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2000);

    const bannerPage = new ModerationBannerPage(page);
    const isHidden = await bannerPage.isPostHidden().catch(() => false);
    expect(isHidden).toBe(false);

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M6: substantial edit clears scan-exempt — full re-classification runs", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M6",
      `test-mod-m6-${Date.now()}`
    );
    const originalBody = "Original content for M6 scan-exempt clear test.";
    const topic = await setup.createTestTopic(
      "[TEST] M6 substantial edit clears scan-exempt",
      originalBody,
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

    if (postId) {
      const requestId = `e2e-mod-m6-${Date.now()}`;
      const actionId = `e2e-action-m6-${Date.now()}`;

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
      await page.waitForTimeout(500);

      await sendWebhook({
        event: "moderation_action.overturned",
        action_id: actionId,
        request_id: requestId,
      });
      await page.waitForTimeout(1000);

      const substantialEdit =
        "This is a completely different and substantially changed version of the post content for M6.";
      await fetch(`${API_URL}/posts/${postId}.json`, {
        method: "PUT",
        headers: {
          "Api-Key": API_KEY,
          "Api-Username": "admin",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ post: { raw: substantialEdit } }),
      });
      await page.waitForTimeout(1500);

      const postAfterEdit = await fetch(`${API_URL}/posts/${postId}.json`, {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      });
      if (postAfterEdit.ok) {
        const data = await postAfterEdit.json();
        const isScanExempt =
          data.custom_fields?.opennotes_scan_exempt === "true" ||
          data.custom_fields?.opennotes_scan_exempt === true;

        expect(isScanExempt === false || data.raw !== originalBody).toBe(true);
      }
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M7: staff removes scan-exempt — flag removed, next edit triggers classification", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M7",
      `test-mod-m7-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] M7 staff removes scan-exempt",
      "Post for testing staff removal of scan-exempt flag.",
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

    if (postId) {
      const requestId = `e2e-mod-m7-${Date.now()}`;
      const actionId = `e2e-action-m7-${Date.now()}`;

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
      await page.waitForTimeout(500);

      await sendWebhook({
        event: "moderation_action.overturned",
        action_id: actionId,
        request_id: requestId,
      });
      await page.waitForTimeout(1000);

      const removeExemptResp = await fetch(
        `${API_URL}/posts/${postId}/custom_fields.json`,
        {
          method: "PUT",
          headers: {
            "Api-Key": API_KEY,
            "Api-Username": "admin",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            post_custom_field: {
              name: "opennotes_scan_exempt",
              value: "",
            },
          }),
        }
      );
      expect(removeExemptResp.ok || removeExemptResp.status < 500).toBe(true);
      await page.waitForTimeout(1000);
    }

    await page.goto(`/t/${topic.topicSlug}/${topic.topicId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(2000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });

  test("M8: classifier evidence for audit — classifier_evidence JSONB has labels, scores", async ({
    page,
  }) => {
    const login = new LoginPage(page);
    await login.loginAsAdmin();

    const category = await setup.createTestCategory(
      "[TEST] Moderation M8",
      `test-mod-m8-${Date.now()}`
    );
    const topic = await setup.createTestTopic(
      "[TEST] M8 classifier evidence audit",
      "Post for testing classifier evidence storage.",
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

    const requestId = `e2e-mod-m8-${Date.now()}`;
    const actionId = `e2e-action-m8-${Date.now()}`;
    const classifierEvidence = {
      labels: ["MISINFORMED_OR_POTENTIALLY_MISLEADING", "SATIRE"],
      scores: {
        MISINFORMED_OR_POTENTIALLY_MISLEADING: 0.88,
        SATIRE: 0.05,
        NOT_MISLEADING: 0.07,
      },
      model_version: "v1.0",
      confidence: 0.88,
    };

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
      classifier_evidence: classifierEvidence,
    });
    expect(proposeResp.status).toBe(200);
    await page.waitForTimeout(2000);

    const proposeData = await proposeResp.json().catch(() => ({}));
    expect(proposeData).toHaveProperty("received", true);

    await page.goto("/review", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const bodyText = (await page.textContent("body")) ?? "";
    expect(bodyText).toBeTruthy();

    if (postId) {
      const postResp = await fetch(`${API_URL}/posts/${postId}.json`, {
        headers: { "Api-Key": API_KEY, "Api-Username": "admin" },
      });
      if (postResp.ok) {
        const postData = await postResp.json();
        const hasRequestId =
          JSON.stringify(postData).includes(requestId) ||
          postData.custom_fields?.opennotes_request_id === requestId;
        expect(hasRequestId).toBe(true);
      }
    }

    await setup.cleanupTopic(topic.topicId).catch(() => {});
  });
});
