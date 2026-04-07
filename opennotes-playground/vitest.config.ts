import path from "node:path";
import { defineConfig } from "vitest/config";
import solidPlugin from "vite-plugin-solid";

export default defineConfig({
  plugins: [solidPlugin()],
  test: {
    exclude: ["tests/**", "node_modules/**"],
    globals: true,
    environmentMatchGlobs: [
      ["src/components/**", "jsdom"],
    ],
    server: {
      deps: {
        inline: [/solid-js/, /@kobalte/, /@solidjs/],
      },
    },
  },
  resolve: {
    conditions: ["development", "browser"],
    alias: {
      "~": path.resolve(__dirname, "src"),
    },
  },
});
