import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { SEED, loginAsSeed, resetDatabase } from "./helpers";

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
  await expect(page.getByText(/kết nối #/)).toBeVisible();
  // Revoking asks first: "Huỷ" keeps the connection working.
  await page.getByRole("button", { name: "Thu hồi kết nối" }).click();
  const confirm = page.getByRole("tooltip").filter({ hasText: "Thu hồi kết nối này?" });
  await confirm.getByRole("button", { name: "Huỷ" }).click();
  await expect(confirm).toBeHidden();
  expect((await rpc()).status()).toBe(200);
  await page.getByRole("button", { name: "Thu hồi kết nối" }).click();
  await confirm.getByRole("button", { name: "Thu hồi", exact: true }).click();
  await expect(page.getByText("Bạn chưa có kết nối nào.")).toBeVisible();
  expect((await rpc()).status()).toBe(401);
});

// The app opens the authorize link in a browser not signed in to Reels Studio (as Claude's popup often is):
// signing in there must come back to the consent screen, not leave the member on the video list.
test("signing in from the authorize page comes back to consent", async ({ page }) => {
  const registered = await page.request.post("/api/mcp/oauth/register", {
    data: { redirect_uris: ["https://claude.ai/api/mcp/auth_callback"], token_endpoint_auth_method: "none" },
  });
  const { client_id } = await registered.json();
  const query = new URLSearchParams({
    client_id,
    redirect_uri: "https://claude.ai/api/mcp/auth_callback",
    response_type: "code",
    resource,
    code_challenge: createHash("sha256").update("b".repeat(43)).digest("base64url"),
    code_challenge_method: "S256",
    scope: "reels:read reels:write",
    state: "e2e-login",
  });
  await page.goto(`/api/mcp/oauth/authorize?${query}`);
  await page.getByRole("link", { name: "Đăng nhập Reels Studio" }).click();
  await expect(page).toHaveURL(/\/login\?/);
  await page.getByLabel("Email").fill(SEED.email);
  await page.getByLabel("Mật khẩu").fill(SEED.password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { name: "Cho phép Claude kết nối?" })).toBeVisible();
});

// A `next` that is not the authorize endpoint is ignored: the login page never sends a member elsewhere.
test("login ignores a next link that is not the authorize endpoint", async ({ page }) => {
  await page.goto("/login?next=" + encodeURIComponent("https://evil.example/"));
  await page.getByLabel("Email").fill(SEED.email);
  await page.getByLabel("Mật khẩu").fill(SEED.password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).toHaveURL(/\/videos$/);
});

// Consent must not be embeddable under another site's UI.
test("the ChatGPT consent page rejects framing", async ({ page }) => {
  await loginAsSeed(page);
  const response = await page.goto("/chatgpt");
  expect(response?.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(response?.headers()["x-frame-options"]).toBe("DENY");
});
