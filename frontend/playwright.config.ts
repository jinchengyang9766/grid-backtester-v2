import { defineConfig, devices } from "@playwright/test";

import { BASE_URL } from "./e2e/fixtures/servers";

/**
 * The E2E suite drives a real Chromium against a real Next.js production
 * server and a real FastAPI backend on a temporary SQLite database, through
 * the same-origin proxy. `global-setup` owns that lifecycle.
 *
 * Retries stay at zero locally so a flaky acceptance run is visible rather
 * than papered over; CI gets one retry for genuine infrastructure noise.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  // Each spec seeds and mutates the same isolated database, so they run
  // sequentially rather than fighting over shared state.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },
  projects: [
    // Chromium is the required acceptance browser.
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
