import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  retries: 1,
  use: {
    baseURL: "http://localhost:3100",
  },
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.02,
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "node tests/mock-server.cjs",
      port: 9999,
      reuseExistingServer: true,
    },
    {
      command:
        "PORT=3100 OPENNOTES_SERVER_URL=http://localhost:9999 pnpm dev",
      port: 3100,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
