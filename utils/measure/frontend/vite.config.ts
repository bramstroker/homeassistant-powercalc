import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "./",
  server: {
    // Forward API and SSE requests to the locally running measure backend so the
    // dev server behaves like the single-origin ingress deployment.
    proxy: {
      "/api": { target: "http://127.0.0.1:8099", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    restoreMocks: true,
  },
});
