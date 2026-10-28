import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

const webDir = process.cwd();

// API_URL may live only in the repo-root .env, which Next.js does not read on its own.
// Variables already set in the environment (E2E, CI) win over the file.
loadEnvConfig(path.resolve(webDir, ".."));

const apiUrl = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // A separate build directory lets the E2E server (next build + next start) run beside next dev.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Keep module resolution inside web/: an old node_modules/ at the repo root must never be picked up.
  turbopack: { root: webDir },
  outputFileTracingRoot: webDir,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
