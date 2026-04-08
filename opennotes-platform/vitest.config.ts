import solid from "vite-plugin-solid";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [solid()],
  resolve: {
    alias: {
      "~": "./src",
    },
  },
  test: {
    environment: "jsdom",
  },
});
