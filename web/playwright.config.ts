import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// E2E runs its own API (8100, database reels_e2e) and its own web build (3100, .next-e2e),
// so it never touches the dev servers (8000/3000) or the dev database, and can run beside them.
const API_DIR = path.resolve(__dirname, "../api");
export const E2E_DATABASE_URL =
  process.env.E2E_DATABASE_URL || "postgresql+psycopg://reels:reels@127.0.0.1:5432/reels_e2e";
export const API_PYTHON = path.join(
  API_DIR,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3100", locale: "vi-VN", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${API_PYTHON}" -m uvicorn reels_api.main:create_app --factory --host 127.0.0.1 --port 8100`,
      cwd: API_DIR,
      url: "http://127.0.0.1:8100/api/me",
      env: { DATABASE_URL: E2E_DATABASE_URL, ALLOWED_ORIGINS: "http://localhost:3100" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx next build && npx next start -p 3100",
      cwd: __dirname,
      url: "http://localhost:3100/login",
      env: { NEXT_DIST_DIR: ".next-e2e", API_URL: "http://127.0.0.1:8100" },
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
