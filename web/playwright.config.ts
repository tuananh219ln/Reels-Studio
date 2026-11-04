import fs from "node:fs";
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

// Fake Claude and Pixabay (api/scripts/fake_services.py), reached only through the base-URL variables.
const FAKES_URL = "http://127.0.0.1:8199";
const BACKEND_ENV = {
  DATABASE_URL: E2E_DATABASE_URL,
  MCP_PUBLIC_URL: "http://localhost:3100/api/mcp",
  STORAGE_DIR: path.resolve(__dirname, ".e2e-data/storage"),
  // Own temp folder: the Pixabay search cache never mixes fake results into the developer's real cache.
  TMP: path.resolve(__dirname, ".e2e-data/tmp"),
  TEMP: path.resolve(__dirname, ".e2e-data/tmp"),
  TMPDIR: path.resolve(__dirname, ".e2e-data/tmp"),
  ANTHROPIC_API_KEY: "fake-claude-key",
  ANTHROPIC_BASE_URL: FAKES_URL,
  PIXABAY_API_KEY: "fake-pixabay-key",
  PIXABAY_API_URL: `${FAKES_URL}/api/`,
  PEXELS_API_KEY: "fake-pexels-key",
  PEXELS_API_URL: `${FAKES_URL}/pexels`,
  // Anonymous Openverse (no client id/secret), as production runs by default.
  OPENVERSE_API_URL: `${FAKES_URL}/openverse`,
  ELEVENLABS_API_KEY: "fake-elevenlabs-key",
  ELEVENLABS_API_URL: FAKES_URL,
  IMAGE_GEN_API_KEY: "fake-image-gen-key",
  IMAGE_GEN_API_URL: `${FAKES_URL}/gemini`,
  // Cloudflare Workers AI, ready for tests; IMAGE_GEN_PROVIDER stays unset, so with both set up Cloudflare is the default.
  IMAGE_GEN_CF_API_URL: `${FAKES_URL}/cloudflare/client/v4`,
  IMAGE_GEN_CF_ACCOUNT_ID: "test-account",
  IMAGE_GEN_CF_API_KEY: "fake-cloudflare-token",
  FACEBOOK_API_URL: `${FAKES_URL}/facebook`,
  SHOPEE_AFFILIATE_API_URL: `${FAKES_URL}/shopee/graphql`,
  SHOPEE_SHORT_LINK_URL: `${FAKES_URL}/shopee-short`,
  PYTHONUNBUFFERED: "1",
  PYTHONIOENCODING: "utf-8",
};
fs.mkdirSync(BACKEND_ENV.TMP, { recursive: true });

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
      // Short scenes (1 s each) keep the E2E render quick.
      command: `"${API_PYTHON}" scripts/fake_services.py 8199 1`,
      cwd: API_DIR,
      url: `${FAKES_URL}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `"${API_PYTHON}" -m uvicorn reels_api.main:create_app --factory --host 127.0.0.1 --port 8100`,
      cwd: API_DIR,
      url: "http://127.0.0.1:8100/api/me",
      env: { ...BACKEND_ENV, ALLOWED_ORIGINS: "http://localhost:3100" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // The real worker with FFmpeg; reels_e2e is migrated by the first test's reset, so it may still be waiting.
      command: `"${API_PYTHON}" -m reels_api worker`,
      cwd: API_DIR,
      env: BACKEND_ENV,
      wait: { stdout: /Worker lock acquired|Table jobs does not exist yet/ },
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
