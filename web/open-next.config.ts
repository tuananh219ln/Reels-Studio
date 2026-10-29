import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// No incremental cache: every app page is rendered per request behind the login.
export default defineCloudflareConfig({});
