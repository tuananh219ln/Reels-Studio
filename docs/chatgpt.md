# ChatGPT and Claude connection

Members can use ChatGPT, Claude (web, Desktop, mobile) or Claude Code to search and read the shared
video library, edit a scene's text, voice text and clip part, edit caption/hashtags/pinned comment,
create a video with a script job or from a script the assistant writes itself, give a scene a photo
or clip from a link, attach approved affiliate products, and request a render.
The API uses the official MCP Python SDK with stateless Streamable HTTP and JSON responses.
There is no additional AI call in the MCP layer: the assistant calls tools, and Reels Studio's existing
worker performs the queued jobs with the team's configured services and their normal costs.

The assistant runs on the member's own plan (ChatGPT, or a Claude Pro/Max plan): each member connects
their own account, and nothing in Reels Studio uses a member's subscription for anyone else.

## Writing scripts on the member's Claude plan, not the team's API key

Where the script is written decides who pays, and the video page says which one wrote it:

| Started from | Written by | Cost | Video page shows |
| --- | --- | --- | --- |
| "Tạo video" in the app (or `create_video` over MCP) | The team's AI service, a script job | API key on Cài đặt › Mô hình AI | "Kịch bản viết bởi Claude · <model>" (provider and model of the job) |
| A chat in Claude (web, Desktop, Claude Code) connected here | The member's own Claude | The member's Pro/Max plan, nothing to the team | "Kịch bản viết bởi Claude của thành viên qua kết nối MCP" |

A topic group's video is written with the group's own prompt either way:

1. `get_script_prompt` (read) returns the exact prompt a script job would send for that topic and group: the
   group's "Prompt viết kịch bản", its banned words and photo hint, "Video xuyên suốt"'s rules when asked, and the
   fixed JSON output format ([content.md](content.md)). Groups without a script prompt are refused, as in the app.
2. The assistant writes the JSON itself, self safety review included.
3. `create_video_from_group_prompt` reads it with the script job's own parser and saves it as the job would: five
   titles, scenes with voice, photo keywords and image prompts, caption, hashtags, pinned comment, self review and
   music ideas; then the team's "Mẫu dựng", the Shopee suggestions and "Tự tìm ảnh" follow as after a job. JSON the
   parser cannot read is refused with the reason, for the assistant to fix. The video is marked
   `videos.written_via = "assistant"` (migration 0056).

The server's instructions make this the default; `create_video` (the team's API) is used only when the member asks
for it. `create_video_from_script` (below) is also marked as written by the member's Claude.

## Product videos with Claude

The tools give the assistant what it needs to make an affiliate product video without the team's AI
service:

1. `list_affiliate_products` finds the team's Shopee/TikTok Shop products (name, price, commission,
   photo and links), approved ones by default.
2. `create_video_from_script` makes a "Tự viết" video from a script the assistant writes: one scene per
   paragraph, `Đọc:` lines as the voice text. No script job, so no cost to the team's AI service.
3. `set_scene_media_from_link` gives a scene a TikTok clip, a video file's link or a photo's link, like
   pasting a link on the video page (same downloads, limits and refusals of local addresses). A clip's
   part is chosen with `update_scene`'s `video_start` and `video_speed` (and `video_sound`, "Tiếng gốc": the
   clip's own sound in the MP4); `add_scene` adds a scene.
   A member's own footage is uploaded on the video page: MCP does not carry files.
4. `set_video_products` attaches approved products (Shopee on a Facebook video, TikTok Shop on its
   TikTok version), whose links go in the pinned comment.
5. `set_scene_motion` turns a scene into a "Cảnh động": the assistant writes HTML + GSAP (a price that pops,
   the product photo flying in) and the worker renders it with HyperFrames into the scene's clip
   ([architecture.md](architecture.md#motion-scenes-hyperframes)). The scene's photo at that moment is available as
   `assets/photo.*`, so attach a transparent product photo first. No cost to the team's AI service.
6. `render_video` queues the render; narration may use ElevenLabs.

## The media library

Members fill "Kho tư liệu" (`/media`) by dragging whole folders of their own footage and product photos, or by
searching the product on Google Ảnh / TikTok from the page and pasting the links back. The assistant reads it with
`list_media` (by folder, kind or name), **looks at the items** with `view_media` before choosing, adds links the
member gives with `add_media_from_links`, and puts an item in a scene with `set_scene_media_from_library` (a copy).

## Editing like the studio, and checking the result

The assistant edits with the studio's own handlers, presets and locks (nothing the web page cannot do):

- `list_edit_options` reads the presets it may use: transitions, colour presets, music levels, layer styles,
  sizes, entrance effects, stickers, sound effects and their volumes, and the team's music library.
- `set_scene_effects` (transition, colour, music level, "Tự khớp lời đọc"; `default` goes back to the video's),
  `reorder_scenes`, `split_scene`, `delete_scene` (content scenes only).
- `add_layer`, `update_layer`, `delete_layer` for text and sticker layers; `add_sound`, `delete_sound`;
  `set_audio` for the music from the library, its volume and the narration on or off.
- **Looking at its work**, like AIEV's "every frame verified": `view_scene` returns the scene's preview frame (the
  photo or the clip's first frame with the scene's text placed as the render places it), and
  `view_render_frames` returns up to eight frames of the rendered MP4 at the seconds it picks, both at 540×960.

The server's instructions hold the team's quality bar: a strong hook in the first two seconds, one idea per scene,
short on-screen text, a clear call to buy; fix every blocking item and warning, look at every scene before
rendering, read the MP4's automatic QC (`mp4.qc`, see [architecture.md](architecture.md#render-qc)) and fix every
failed check, look at the MP4's frames after it, and say the video is done only once it has, listing what it checked.

## Enable and connect

1. Deploy the PR through the normal CI process; migration `0021` creates the OAuth tables.
2. The owner sets `MCP_PUBLIC_URL=https://<web-domain>/api/mcp` on the **api** application.
   The origin must already be in `ALLOWED_ORIGINS`. Leave the variable empty to disable MCP.
   Use the public **web** domain, not the backend domain: browser login, consent and MCP discovery
   use the same origin. HTTPS is required except on localhost/127.0.0.1 for development.
3. Sign in to Reels Studio and open **Cài đặt → Kết nối ChatGPT / Claude** (`/chatgpt`). Copy the
   server URL.
4. Add it to the assistant:
   - **ChatGPT:** in the apps/plugins settings, add a custom MCP server with that URL and choose
     **OAuth**. The workspace owner may need to allow custom connections.
   - **Claude (web, Desktop):** Settings › Connectors › add a custom connector with that URL.
   - **Claude Code:** `claude mcp add --transport http reels-studio <URL>`, then `/mcp` to sign in.

   This server supports dynamic client registration (DCR), public clients and S256 PKCE; it does not
   support CIMD or a client secret, so Claude falls back to DCR.
5. Connect and sign in to Reels Studio if asked. The login opens in another tab; return to the
   authorization tab and choose **Tôi đã đăng nhập, tiếp tục**. Complete any required password
   change before proceeding. The consent screen identifies your account and the requested access.
6. Choose **Cho phép kết nối**. ChatGPT receives OAuth credentials, never the member's password,
   Reels Studio cookie, AI API keys, or Facebook tokens.
7. Select the connection in a ChatGPT conversation and ask it to use Reels Studio.

ChatGPT UI labels and account availability may vary. The setup follows OpenAI's
[custom MCP connection](https://developers.openai.com/api/docs/guides/custom-mcp-server) and
[authentication](https://developers.openai.com/plugins/build/auth) documentation. Issuer
identification is enabled, so ChatGPT's redirect URI is
`https://chatgpt.com/connector_platform_oauth_redirect`. Claude's follow Anthropic's
[connector authentication](https://claude.com/docs/connectors/building/authentication) page:
`https://claude.ai/api/mcp/auth_callback` for the hosted apps (and `https://claude.com/...`, where it
may move), and for Claude Code a loopback `http://localhost:<port>/callback` or
`http://127.0.0.1:<port>/callback` whose port changes every session. A client may register up to
four of these and nothing else. A loopback callback matches its registered host and path on any
port; each grant keeps the exact callback it was asked for (`mcp_authorizations.redirect_uri`,
migration 0047) and the code exchange must name that one. The consent screen names the app and the
callback's host, and warns for a loopback one, as the MCP specification asks. If an app displays
another URI, do not broaden the allowlist blindly: check its documentation first.

## Example requests

- “Tìm các video về xương khớp, cho tôi biết video nào còn thiếu ảnh.”
- “Đọc video số 12 và đề xuất ba câu mở đầu. Chưa lưu.”
- “Lưu câu thứ hai vào cảnh tiêu đề của video 12.”
- “Sửa lời đọc cảnh 45 thành: Ăn đa dạng giúp bổ sung nhiều chất dinh dưỡng.”
- “Viết kịch bản về rau xanh theo prompt nhóm Sức khỏe và tạo video.” (the member's Claude writes it)
- “Tạo video về rau xanh trong nhóm chủ đề Sức khỏe bằng API của nhóm.” (a script job, paid)
- “Tìm sản phẩm nồi chiên đã duyệt, viết kịch bản 5 cảnh (hook, lợi ích, giá, kêu gọi mua) và tạo
  video tự viết trong nhóm Gia dụng.”
- “Gắn clip TikTok này cho cảnh 2, bắt đầu từ giây 4: https://www.tiktok.com/@shop/video/…”
- “Gắn sản phẩm đó vào video rồi render.”
- “Render video 12; tôi đồng ý dùng giọng đọc ElevenLabs nếu còn thiếu.”
- “Kiểm tra video 12 đã render xong chưa.”

These are requests to ChatGPT, not deterministic commands. Read the proposed changes before
approving a write tool in ChatGPT. Content returned by the tools is data, not tool instructions.
The connector has no tools to post to Facebook, delete videos, manage users, modify prompts or
credentials, or retrieve file bytes. Its `editor_url` opens the app; preview/download URLs still
need a normal browser login. Listing has a maximum page size of 50; use `offset` to continue.

## Authorization and revocation

- `reels:read` reads video content/status, topic-group names, a group's assembled script prompt and the affiliate product list (no
  member's affiliate account or key). `reels:write` additionally permits
  the explicit write tools. Both use the member's identity; the library is shared by the team.
- Consent is explicit, protected by the existing Origin guard and a short-lived ticket bound to
  the member's current browser session. The web page rejects framing (CSP/X-Frame-Options). A denied/used ticket cannot be reused. Authorization
  codes expire after two minutes and are consumed under a database lock after S256 verification.
- Access tokens last at most one hour. Refresh rotates both tokens and lasts at most 30 days from
  the original grant. Refreshing does not extend the connection or its underlying login session.
- All tickets/codes/access/refresh tokens are stored only as SHA-256 hashes. The resource URL is
  bound to the authorization and connection; changing the configured URL requires reconnecting.
- **Cài đặt → Kết nối ChatGPT / Claude → Thu hồi kết nối** revokes one of your connections. Other members
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
