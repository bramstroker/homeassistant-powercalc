import { defineConfig, devices } from "@playwright/test";

const PORT = 5174;

/**
 * Browser tests run against the Vite dev server with the API mocked in the page, so no
 * Python backend, Home Assistant connection or measurement hardware is needed.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // Bind IPv4 explicitly: left to itself Vite listens on [::1] only, which the IPv4
    // baseURL below cannot reach.
    command: `npx vite --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    stdout: "ignore",
  },
});
