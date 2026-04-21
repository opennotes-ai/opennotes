import { defineConfig } from "tsup";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    "components/index": "src/components/index.ts",
    "utils/index": "src/utils/index.ts",
    "palettes/index": "src/palettes/index.ts",
  },
  format: ["esm"],
  target: "es2022",
  dts: true,
  clean: true,
  sourcemap: true,
  treeshake: true,
  external: [
    "solid-js",
    "solid-js/web",
    "solid-js/store",
    "solid-js/html",
    "@kobalte/core",
    "class-variance-authority",
    "clsx",
    "tailwind-merge",
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
