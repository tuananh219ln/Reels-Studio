import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Existing code breaks these React Compiler rules in a few places (load-on-mount effects, a ref read
    // in AutoSaveField). Fixing them changes component behaviour, so they warn until that is done.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
    },
  },
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
