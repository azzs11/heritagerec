import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the real server and data, never a mocked API. Both servers are started here
// unless they are already running (then they are reused).
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } },
    { name: "phone", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true } },
  ],
  webServer: [
    // In CI there is no Java and no corpus snapshot: the server starts without keyword search, and the tests that
    // need it or the corpus skip themselves; every graph, atlas, layout and accessibility check still runs.
    {
      command: `cd .. && uv run python -m server${process.env.CI ? " --no-keyword" : ""}`,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 180_000,
    },
    { command: "npm run dev", url: "http://localhost:3000", reuseExistingServer: true, timeout: 120_000 },
  ],
});
