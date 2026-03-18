import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  retries: 1,
  use: {
    baseURL: "http://localhost:3100",
  },
  webServer: [
    {
      command: "node tests/mock-server.cjs",
      port: 9999,
      reuseExistingServer: false,
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
