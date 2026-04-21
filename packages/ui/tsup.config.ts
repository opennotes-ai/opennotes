import { defineConfig } from "tsup";

export default defineConfig({
  entry: [
    "src/index.ts",
    "src/components/index.ts",
    "src/components/*.tsx",
    "src/components/ui/*.tsx",
    "src/utils/index.ts",
    "src/utils/*.ts",
    "src/palettes/index.ts",
    "src/palettes/*.ts",
    "!src/**/*.test.ts",
    "!src/**/*.test.tsx",
  ],
  format: ["esm"],
  target: "es2022",
  dts: true,
  clean: true,
  sourcemap: true,
  splitting: false,
  treeshake: false,
  bundle: false,
  external: [
    "solid-js",
    "solid-js/web",
    "solid-js/store",
    "solid-js/html",
    "@solidjs/router",
    "@kobalte/core",
    "class-variance-authority",
    "clsx",
    "tailwind-merge",
    "echarts",
    "echarts/core",
    "echarts/charts",
    "echarts/components",
    "echarts/renderers",
    "@opennotes/tokens",
  ],
  esbuildOptions(options) {
    options.jsx = "preserve";
    options.jsxImportSource = "solid-js";
  },
  outExtension() {
    return { js: ".js" };
  },
});
