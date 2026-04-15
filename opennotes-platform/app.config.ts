import { defineConfig } from "@solidjs/start/config";

export default defineConfig({
  server: {
    preset: "node-server",
  },
  middleware: "src/middleware/index.ts",
  vite: {
    server: {
      port: 3200,
    },
  },
});
