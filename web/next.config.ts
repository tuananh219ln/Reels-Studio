import { readFileSync } from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

const webDir = process.cwd();

/**
 * Reads a variable the way the api and worker do: a real environment variable wins, otherwise the
 * repo-root .env. Next.js only loads .env files from web/ (and caches that), so it cannot do this.
 */
function rootEnv(name: string): string | undefined {
  if (process.env[name] !== undefined) {
    return process.env[name];
  }
  let text: string;
  try {
    text = readFileSync(path.resolve(webDir, "..", ".env"), "utf8").replace(/^﻿/, "");
  } catch {
    return undefined;
  }
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([\w.]+)\s*=\s*(.*?)\s*$/);
    if (match && match[1] === name) {
      return match[2].replace(/^(['"])(.*)\1$/, "$2");
    }
  }
  return undefined;
}

const apiUrl = (rootEnv("API_URL") || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // A separate build directory lets the E2E server (next build + next start) run beside next dev.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Keep module resolution inside web/: an old node_modules/ at the repo root must never be picked up.
  turbopack: { root: webDir },
  outputFileTracingRoot: webDir,
  async headers() {
    return [
      // The consent screen and the connections: never embeddable under another site's UI.
      ...["/chatgpt", "/settings/mcp"].map((source) => ({
        source,
        headers: [
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      })),
    ];
  },
  async redirects() {
    // "Kết nối ChatGPT / Claude" moved into Cấu hình as "Kết nối MCP"; old links (and the browser's #ticket) still arrive there.
    return [{ source: "/chatgpt", destination: "/settings/mcp", permanent: false }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      {
        source: "/.well-known/oauth-protected-resource/api/mcp",
        destination: `${apiUrl}/.well-known/oauth-protected-resource/api/mcp`,
      },
      {
        source: "/.well-known/oauth-authorization-server/api/mcp/oauth",
        destination: `${apiUrl}/.well-known/oauth-authorization-server/api/mcp/oauth`,
      },
    ];
  },
};

export default nextConfig;
