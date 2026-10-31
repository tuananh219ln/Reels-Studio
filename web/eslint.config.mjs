import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    ".next-e2e/**",
    ".open-next/**",
    ".wrangler/**",
    ".e2e-data/**",
    "test-results/**",
    "playwright-report/**",
    "next-env.d.ts",
  ]),
]);
