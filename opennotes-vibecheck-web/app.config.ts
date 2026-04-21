import { defineConfig } from "@solidjs/start/config";

export default defineConfig({
  server: {
    preset: "node-server",
  },
  vite: {
    server: {
      port: 3200,
    },
  },
});
