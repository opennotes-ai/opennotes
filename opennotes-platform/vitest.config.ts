// Platform vitest config.
//
// We consume @opennotes/ui primitives (Solid components) from tests, so the
// vite-plugin-solid JSX transform is required. Note: vite-plugin-solid@2.11+
// auto-injects `@testing-library/jest-dom/vitest` into setupFiles when it can
// resolve the package; to make that behaviour explicit (and survive plugin
// upgrades that change the auto-inject heuristic), we set setupFiles ourselves
// below. When adding more setup, extend the setupFiles array rather than
// relying on the plugin's auto-inject.
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";

export default defineConfig({
  plugins: [solid()],
  resolve: {
    alias: {
      "~": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["@testing-library/jest-dom/vitest"],
    exclude: ["**/node_modules/**", "**/dist/**", "tests/**"],
  },
});
