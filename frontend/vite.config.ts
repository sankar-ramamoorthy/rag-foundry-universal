import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Development proxy: browser paths are /v1/product/* in development and in
// production. The orchestrator address comes from the environment; the
// localhost default carries no personal or private address.
const target = process.env.FOUNDRY_API_URL ?? "http://localhost:8004";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/v1/product": { target, changeOrigin: false } } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
