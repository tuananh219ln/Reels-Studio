import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

const origin = "http://localhost:3100";
const resource = origin + "/api/mcp";
const callback = "https://chatgpt.com/connector_platform_oauth_redirect";

test.beforeEach(() => resetDatabase());

test("ChatGPT connects through consent, then the member revokes it", async ({ page }) => {
  await loginAsSeed(page);
  const metadata = await page.request.get("/.well-known/oauth-protected-resource/api/mcp");
  expect(metadata.status()).toBe(200);
  expect((await metadata.json()).resource).toBe(resource);
  const registered = await page.request.post("/api/mcp/oauth/register", {
    data: { redirect_uris: [callback], token_endpoint_auth_method: "none" },
  });
  expect(registered.status()).toBe(201);
  const { client_id } = await registered.json();
  const verifier = "a".repeat(43);
  const query = new URLSearchParams({
    client_id,
    redirect_uri: callback,
    response_type: "code",
    resource,
    code_challenge: createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
    scope: "reels:read reels:write",
    state: "e2e-state",
  });
  await page.goto(`/api/mcp/oauth/authorize?${query}`);
  await expect(page.getByRole("heading", { name: "Cho phép ChatGPT kết nối?" })).toBeVisible();
  await expect(page.getByText(/phí dịch vụ AI/)).toBeVisible();
  // Capture our callback in the browser; no request reaches ChatGPT or any real provider.
  await page.route("https://chatgpt.com/**", (route) =>
    route.fulfill({ contentType: "text/plain", body: "Callback captured" }),
  );
  await page.screenshot({ path: "test-results/chatgpt-consent.png", fullPage: true });
  await page.getByRole("button", { name: "Cho phép kết nối" }).click();
  await expect(page).toHaveURL(/https:\/\/chatgpt.com\/connector_platform_oauth_redirect\?/);
  const code = new URL(page.url()).searchParams.get("code");
  expect(code).toBeTruthy();
  const tokenResponse = await page.request.post(origin + "/api/mcp/oauth/token", {
    form: {
      grant_type: "authorization_code",
      client_id,
      code: code!,
      code_verifier: verifier,
      redirect_uri: callback,
      resource,
    },
  });
  expect(tokenResponse.status()).toBe(200);
  const { access_token } = await tokenResponse.json();
  const rpc = () =>
    page.request.post(origin + "/api/mcp", {
      headers: { Authorization: `Bearer ${access_token}`, Accept: "application/json, text/event-stream" },
      data: { jsonrpc: "2.0", id: 1, method: "tools/list" },
    });
  expect((await rpc()).status()).toBe(200);
  await page.goto("/chatgpt");
  await expect(page.getByText(/Kết nối #/)).toBeVisible();
  await page.getByRole("button", { name: "Thu hồi kết nối" }).click();
  await expect(page.getByText("Bạn chưa có kết nối ChatGPT nào.")).toBeVisible();
  expect((await rpc()).status()).toBe(401);
});
