import { configDefaults, defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";
import { fileURLToPath } from "node:url";

// Gate eval-test exclusion on an env var so the default vitest run skips
// fixture-writing eval suites, while explicit invocations can opt back in.
// To run an eval test:  RUN_EVAL_TESTS=1 pnpm exec vitest run tests/eval/<file>.eval.test.tsx
const includeEvalTests = process.env.RUN_EVAL_TESTS === "1";

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
    exclude: includeEvalTests
      ? configDefaults.exclude
      : [...configDefaults.exclude, "**/*.eval.test.{ts,tsx}"],
  },
});
