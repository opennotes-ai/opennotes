import { DiscourseAPI } from "./helpers/discourse-api";
import { TestSetup } from "./helpers/test-setup";
import { ADMIN, REVIEWER1, REVIEWER2, NEWUSER } from "./fixtures/users";

const DISCOURSE_URL = process.env.DISCOURSE_URL || "http://localhost:4200";
const API_USERNAME = process.env.DISCOURSE_API_USERNAME || "admin";

async function getApiKey(): Promise<string> {
  const envKey = process.env.DISCOURSE_API_KEY;
  if (envKey) return envKey;

  // Try reading auto-provisioned key from bootstrap
  const fs = await import("fs");
  const keyPath = new URL(
    "../../docker/.discourse-api-key",
    import.meta.url
  ).pathname;
  try {
    return fs.readFileSync(keyPath, "utf-8").trim();
  } catch {
    throw new Error(
      "DISCOURSE_API_KEY not set and no auto-provisioned key found.\n" +
        "Run: mise run discourse:bootstrap (provisions a key automatically)\n" +
        "Or: export DISCOURSE_API_KEY=<your-key>"
    );
  }
}

async function globalSetup() {
  console.log("\n==> Playwright global setup");

  // 1. Check Discourse is running
  console.log(`Checking Discourse at ${DISCOURSE_URL}...`);
  const maxRetries = 5;
  let discourseReady = false;

  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(`${DISCOURSE_URL}/srv/status`);
      if (response.ok) {
        discourseReady = true;
        break;
      }
    } catch {
      // Discourse not ready yet
    }
    if (i < maxRetries - 1) {
      console.log(
        `  Discourse not ready, retrying in 5s... (${i + 1}/${maxRetries})`
      );
      await new Promise((r) => setTimeout(r, 5000));
    }
  }

  if (!discourseReady) {
    throw new Error(
      `Discourse not available at ${DISCOURSE_URL}. Start it with: mise run discourse:up`
    );
  }
  console.log("  Discourse is running.");

  // 2. Ensure test data is seeded (idempotent)
  const API_KEY = await getApiKey();
  console.log("  API key loaded.");
  const api = new DiscourseAPI(DISCOURSE_URL, API_KEY, API_USERNAME);
  const setup = new TestSetup(api);

  console.log("Ensuring test users exist...");
  await setup.ensureUsersExist([REVIEWER1, REVIEWER2, NEWUSER]);

  // 3. Clean up leftover test topics from previous runs
  console.log("Cleaning up old test topics...");
  try {
    const apiKey = await getApiKey();
    const response = await fetch(
      `${DISCOURSE_URL}/search.json?q=%5BTEST%5D`,
      {
        headers: {
          "Api-Key": apiKey,
          "Api-Username": API_USERNAME,
        },
      }
    );
    if (response.ok) {
      const data = await response.json();
      const topics = data.topics || [];
      for (const topic of topics) {
        if (topic.title?.startsWith("[TEST]")) {
          await api.deleteTopic(topic.id);
          console.log(`  Deleted test topic: ${topic.title}`);
        }
      }
    }
  } catch {
    console.log("  Could not clean up test topics (non-fatal)");
  }

  console.log("==> Global setup complete\n");
}

export default globalSetup;
