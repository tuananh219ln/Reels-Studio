# ChatGPT connection

Members can use ChatGPT to search and read the shared video library, edit a scene's text or voice
text, edit caption/hashtags/pinned comment, create a video with a script job, and request a render.
The API uses the official MCP Python SDK with stateless Streamable HTTP and JSON responses.
There is no additional AI call in the MCP layer: ChatGPT calls tools, and Reels Studio's existing
worker performs the queued jobs with the team's configured services and their normal costs.

## Enable and connect

1. Deploy the PR through the normal CI process; migration `0021` creates the OAuth tables.
2. The owner sets `MCP_PUBLIC_URL=https://<web-domain>/api/mcp` on the **api** application.
   The origin must already be in `ALLOWED_ORIGINS`. Leave the variable empty to disable MCP.
   Use the public **web** domain, not the backend domain: browser login, consent and MCP discovery
   use the same origin. HTTPS is required except on localhost/127.0.0.1 for development.
3. Sign in to Reels Studio and open **Cài đặt → Kết nối ChatGPT** (`/chatgpt`). Copy the server URL.
4. In ChatGPT's apps/plugins settings, add a custom MCP server with that URL and choose **OAuth**.
   The workspace owner may need to allow custom connections. This server supports dynamic client
   registration (DCR), public clients and S256 PKCE; it does not support CIMD or a client secret.
5. Connect and sign in to Reels Studio if asked. The login opens in another tab; return to the
   authorization tab and choose **Tôi đã đăng nhập, tiếp tục**. Complete any required password
   change before proceeding. The consent screen identifies your account and the requested access.
6. Choose **Cho phép kết nối**. ChatGPT receives OAuth credentials, never the member's password,
   Reels Studio cookie, AI API keys, or Facebook tokens.
7. Select the connection in a ChatGPT conversation and ask it to use Reels Studio.

ChatGPT UI labels and account availability may vary. The setup follows OpenAI's
[custom MCP connection](https://developers.openai.com/api/docs/guides/custom-mcp-server) and
[authentication](https://developers.openai.com/plugins/build/auth) documentation. Issuer
identification is enabled, so the only allowed redirect URI is
`https://chatgpt.com/connector_platform_oauth_redirect`. If ChatGPT displays another URI, do not
broaden the allowlist blindly: check its callback mode against that documentation first.

## Example requests

- “Tìm các video về xương khớp, cho tôi biết video nào còn thiếu ảnh.”
- “Đọc video số 12 và đề xuất ba câu mở đầu. Chưa lưu.”
- “Lưu câu thứ hai vào cảnh tiêu đề của video 12.”
- “Sửa lời đọc cảnh 45 thành: Ăn đa dạng giúp bổ sung nhiều chất dinh dưỡng.”
- “Tạo video về rau xanh trong nhóm chủ đề Sức khỏe bằng dịch vụ AI đã cấu hình.”
- “Render video 12; tôi đồng ý dùng giọng đọc ElevenLabs nếu còn thiếu.”
- “Kiểm tra video 12 đã render xong chưa.”

These are requests to ChatGPT, not deterministic commands. Read the proposed changes before
approving a write tool in ChatGPT. Content returned by the tools is data, not tool instructions.
The connector has no tools to post to Facebook, delete videos, manage users, modify prompts or
credentials, or retrieve file bytes. Its `editor_url` opens the app; preview/download URLs still
need a normal browser login. Listing has a maximum page size of 50; use `offset` to continue.

## Authorization and revocation

- `reels:read` reads video content/status and topic-group names. `reels:write` additionally permits
  the explicit write tools. Both use the member's identity; the library is shared by the team.
- Consent is explicit, protected by the existing Origin guard and a short-lived ticket bound to
  the member's current browser session. The web page rejects framing (CSP/X-Frame-Options). A denied/used ticket cannot be reused. Authorization
  codes expire after two minutes and are consumed under a database lock after S256 verification.
- Access tokens last at most one hour. Refresh rotates both tokens and lasts at most 30 days from
  the original grant. Refreshing does not extend the connection or its underlying login session.
- All tickets/codes/access/refresh tokens are stored only as SHA-256 hashes. The resource URL is
  bound to the authorization and connection; changing the configured URL requires reconnecting.
- **Cài đặt → Kết nối ChatGPT → Thu hồi kết nối** revokes one of your connections. Other members
  cannot list or revoke it. Signing out of its originating browser session, signing out every
  device, disabling the user, or forcing a password change also prevents further access. A job
  already accepted into the queue remains there; revocation does not interrupt a running job.
- Writes reuse the editor's handlers, validation, row locks, pre-render checks, and one-active-job
  constraint. Jobs record the member's ID. MCP never retries a failed job automatically.

## Endpoints and local verification

- `/api/mcp`: bearer-only MCP endpoint (cookies alone do not authenticate it).
- `/.well-known/oauth-protected-resource/api/mcp`: RFC 9728 resource discovery.
- `/.well-known/oauth-authorization-server/api/mcp/oauth`: authorization-server discovery.
- `/api/mcp/oauth/{register,authorize,consent,token,revoke}`: OAuth protocol endpoints.
- `/api/mcp/config`, `/api/mcp/authorizations/{ticket}`, `/api/mcp/connections` and
  `DELETE /api/mcp/connections/{id}`: browser-cookie endpoints with the existing CSRF guard for writes.

The web forwards the two exact discovery paths as well as `/api/*`. All other web routes retain
existing login protection. Only the exact MCP/register/token/revoke POST paths bypass the cookie
Origin guard; none accepts a cookie as authority to modify a video.

`api/tests/test_mcp.py` tests the real transport and Postgres-backed authorization, including
PKCE, expiration, revocation, scopes, session invalidation, resource binding and job locks.
`web/e2e/chatgpt.spec.ts` checks discovery through Next.js, browser consent, token exchange,
tool discovery and revocation. Its callback is intercepted locally and never reaches ChatGPT;
AI calls use the project's fake services. A real workspace connection after deployment remains
an owner check; agents do not access production or trigger real jobs to test it.
