import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8000;
const WEB_PORT = 5173;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://localhost:${String(WEB_PORT)}`,
    trace: "retain-on-failure",
    // The view then moves to the routes at once instead of flying there.
    contextOptions: { reducedMotion: "reduce" },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // The real API, answering from the recorded upstream responses (SPEC section 10).
      command: `uv run python manage.py runserver localhost:${String(API_PORT)} --noreload`,
      cwd: "../backend",
      url: `http://localhost:${String(API_PORT)}/api/health`,
      env: {
        DEBUG: "true",
        PROVIDERS_MODE: "fixtures",
        RATE_LIMIT_ENABLED: "false",
        SECRET_KEY: "e2e-only-not-a-secret",
      },
      reuseExistingServer: !process.env.CI,
    },
    {
      // The development server: it exposes the map to the test, which a build does not.
      command: `npm run dev -- --port ${String(WEB_PORT)} --strictPort`,
      url: `http://localhost:${String(WEB_PORT)}`,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
