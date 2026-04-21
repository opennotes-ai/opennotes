import { defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";

export default defineConfig({
  plugins: [solid()],
  resolve: {
    alias: {
      "~": "./src",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["@testing-library/jest-dom/vitest"],
  },
});
