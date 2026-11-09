# ChatGPT and Claude connection

Members can use ChatGPT, Claude (web, Desktop, mobile), Claude Code or Muse (Meta's assistant) to search and read the shared
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
| A chat in an assistant connected here (ChatGPT, Claude, Claude Code, Muse) | The member's own assistant | The member's own plan, nothing to the team | "Kịch bản viết bởi <assistant> của thành viên qua kết nối MCP", e.g. "Muse của thành viên…" ("Trợ lý AI" for videos made before 2026-11-08) |

A topic group's video is written with the group's own prompt either way:

1. `get_script_prompt` (read) returns the exact prompt a script job would send for that topic and group, built by
   the job's own `jobs.script_prompt`: the group's "Prompt viết kịch bản", its banned words and photo hint, and
   the fixed JSON output format ([content.md](content.md)). Its options match "Tạo video":
   - `plan_item_id`: a 30-day plan idea, listed by `list_plan_ideas` (ideas with no video yet): its pain group,
     pain and hook fill the prompt, its topic is used when none is given, and the new video is linked to it. An
     idea of another group or one that already has a video is refused.
   - `ai_effects` ("AI gợi ý hiệu ứng"): the prompt asks for each scene's effects, and they are put on as after a
     job, values outside the presets left out.
   - `video_mode` `single` ("Video xuyên suốt") adds its rules.

   Groups without a script prompt are refused, as in the app.
2. The assistant writes the JSON itself, self safety review included.
3. `create_video_from_group_prompt`, called with the same options, reads it with the script job's own parser and saves it as the job would: five
   titles, scenes with voice, photo keywords and image prompts, caption, hashtags, pinned comment, self review and
   music ideas; then the team's "Mẫu dựng", the Shopee suggestions and "Tự tìm ảnh" follow as after a job. JSON the
   parser cannot read is refused with the reason, for the assistant to fix. The video is marked
   `videos.written_via = "assistant"` (migration 0056) and `videos.assistant_app` names the assistant of the
   connection (migration 0059, from the client's registered callback, `mcp_auth.app_of`); the lists tag it
   "<assistant> (MCP)".

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
  sizes, entrance effects, stickers, sound effects and their volumes, the team's music library, and
  `video_options`: what each setting of the video's "Thiết lập" tab accepts (`video_options.choices()`, built
  from the same lists the tab's save checks).
- `set_video_options` changes a video's "Thiết lập" settings (voice, reading speed and volume, pause after the
  narration, ducking, transition, motion, zoom, text box and title looks, captions, text sizes, text position).
  Only the arguments sent change; it goes through the same `PATCH /videos/{id}` handler and `video_options.clean`
  as the tab, so one wrong value saves nothing. A voice id is checked for its form only (a bare ElevenLabs id or
  `vieneu:<id>`), as on the web; a voice that does not exist fails when the narration is made. It makes no
  narration and never touches the member's defaults or another video. It returns the video's whole `options`.
- `set_scene_effects` (transition, colour, music level, "Tự khớp lời đọc"; `default` goes back to the video's),
  `reorder_scenes`, `split_scene`, `delete_scene` (content scenes only).
- **"Mẫu dựng"** (part 5 of [docs/specs/per-user-settings-ownership](specs/per-user-settings-ownership/brief.md)):
  `list_templates` (read) lists the app's own template, the member's own and those a topic group holds, each with
  its scope (`app`, `personal`, `group`), its groups (and whether it is a group's default), its transitions, whether
  it adds a sound to every scene and an end line, and `video_mode` (always null: a template fits either kind);
  `apply_template_to_video` (write) puts one on a video through the same `POST /api/edit-templates/apply` as "Tự
  dựng": it is the template chosen on the video, it replaces the one the video wore (its sounds and end layers are
  taken off first), and its end line never goes on the script's call-to-action scene; `save_video_as_template`
  (write) saves a video's look as a new template of the member's own, under a name that must not be taken (a taken
  one is refused and the old template stays). No tool deletes or edits a template. Which template to pick or save
  is the assistant's call, by the rules in the tools' descriptions (the video's group's first, then the member's own;
  save only from a rendered video that passed the frame checks; name every template used or made in its report).
- Deleting through MCP (`delete_scene`, `delete_layer`, `delete_sound`) works only on the connected member's own
  videos (part 4, [architecture.md](architecture.md#web-app-and-auth)).
- `add_layer`, `update_layer`, `delete_layer` for text and sticker layers and half-frame photos on a "Video xuyên suốt" (`kind` "photo": the scene's own photo at 1080×960; only `y`, `start`, `seconds` change); `add_sound`, `delete_sound`;
  `set_audio` for the music from the library, its volume and the narration on or off.
- **Looking at its work**, like AIEV's "every frame verified": `view_scene` returns the scene's preview frame (the
  photo or the clip's first frame with the scene's text placed as the render places it), and
  `view_render_frames` returns up to eight frames of the rendered MP4 at the seconds it picks, both at 540×960.
- **Finding a photo for each scene**: `search_stock_photos` searches Pexels, Pixabay or Openverse (free for
  commercial use, no watermark) like "Tìm ảnh" and returns up to six numbered previews to look at, and
  `use_stock_photo` stores the one chosen (only a result of that same search). The server's instructions say to try
  these first, to search the web only when the member asks or the libraries have nothing, preferring Creative Commons
  photos, attached with `set_scene_media_from_link`, and to stop and tell the member at a CAPTCHA.
- **Cleaning a photo or clip**: `view_scene_photo` returns the photo as stored with its size (and the writing "Tìm
  chữ/logo tự động" found); `edit_scene_image` queues "Sửa ảnh" (`lama`, free, or `cloudflare` with boxes; `gemini`
  with words, paid), `restore_scene_image` brings back the original, and `set_scene_clip_blur` blurs boxes on a clip.
  A stock site's watermarked preview is dropped for another photo, never erased.

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
5. Connect and sign in to Reels Studio if asked: **Đăng nhập Reels Studio** opens the login in the same
   tab (`/login?next=...`), and once signed in (and any required password change done) it comes back to
   the authorization request by itself. The login and password pages follow `next` only to
   `/api/mcp/oauth/authorize?...`, never elsewhere. **Tôi đã đăng nhập, tiếp tục** remains for a member who
   signed in another way. The consent screen is the authorize response itself (server-rendered, no script):
   it names your account, the app, the callback's host and the requested access. It used to be a hop to
   the web page `/chatgpt#ticket=...`, where the consent never showed in production, so nothing now
   stands between the request and the screen. **Kết nối ChatGPT / Claude** only lists and revokes
   connections; opening it by hand never asks for consent.
6. Choose **Cho phép kết nối**. The answer is a short page that sends the browser on to the app's callback (a
   refresh, and a link to click if it does not). **No OAuth step answers with an HTTP redirect**: in production
   the web app runs on Cloudflare through OpenNext, whose `/api` proxy fetches the API and follows redirects
   itself, so a 303 was followed server-side (the member saw Claude's "Page not found" on
   `/api/mcp/oauth/consent`, and earlier `/chatgpt` with no ticket on `/authorize`). CI's E2E runs `next start`,
   which does not follow them, so it cannot catch this; `test_mcp.py` asserts the pages instead.
   The app receives OAuth credentials, never the member's password, Reels Studio cookie, AI API keys, or
   Facebook tokens.
7. Select the connection in a ChatGPT conversation and ask it to use Reels Studio.

ChatGPT UI labels and account availability may vary. The setup follows OpenAI's
[custom MCP connection](https://developers.openai.com/api/docs/guides/custom-mcp-server) and
[authentication](https://developers.openai.com/plugins/build/auth) documentation. Issuer
identification is enabled, so ChatGPT's redirect URI is
`https://chatgpt.com/connector_platform_oauth_redirect`. Claude's follow Anthropic's
[connector authentication](https://claude.com/docs/connectors/building/authentication) page:
`https://claude.ai/api/mcp/auth_callback` for the hosted apps (and `https://claude.com/...`, where it
may move), and for Claude Code a loopback `http://localhost:<port>/callback` or
`http://127.0.0.1:<port>/callback` whose port changes every session. Muse's is exactly
`https://agent.meta.ai/api/hatch/oauth/callback`, read from the refused-registration log below (no other
path on that host is accepted). A client may register up to
four of these and nothing else. A loopback callback matches its registered host and path on any
port; each grant keeps the exact callback it was asked for (`mcp_authorizations.redirect_uri`,
migration 0047) and the code exchange must name that one. The consent screen names the app and the
callback's host, and warns for a loopback one, as the MCP specification asks. If an app displays
another URI, do not broaden the allowlist blindly: check its documentation first.

A refused registration is logged by the api as one WARNING line (WARNING because the api runs plain
uvicorn, which prints no INFO line of the app's own loggers), kept for good as an audit of refused
clients and as the way a new app's exact callback is learnt before it is added:
`MCP registration refused: redirect_uris=['…'] client_name='…' token_endpoint_auth_method='…' grant_types=[…] response_types=[…]`.
An authorize request naming a client that never registered (one that skips registration) logs
`MCP authorize from an unknown client: client_id='…' redirect_uri='…'`. Only public client metadata is
logged, each value cut to 300 characters. In production, read it in Coolify › the `api` application ›
Logs, searching for `MCP registration refused` or `MCP authorize from an unknown client`. Add only the
exact URI seen there to the allowlist.

## Example requests

- “Tìm các video về xương khớp, cho tôi biết video nào còn thiếu ảnh.”
- “Đọc video số 12 và đề xuất ba câu mở đầu. Chưa lưu.”
- “Lưu câu thứ hai vào cảnh tiêu đề của video 12.”
- “Sửa lời đọc cảnh 45 thành: Ăn đa dạng giúp bổ sung nhiều chất dinh dưỡng.”
- “Viết kịch bản về rau xanh theo prompt nhóm Sức khỏe và tạo video.” (the member's Claude writes it)
- “Làm video cho ý tưởng ngày 3 trong kế hoạch nhóm Sức khỏe, cho AI chọn hiệu ứng.”
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
  the member's current browser session, carried in the consent page's form. The page rejects framing (CSP
  `frame-ancestors 'none'`), lets its form go only to this site and the callback's origin (`form-action`), and
  uses `Referrer-Policy: same-origin` so the browser sends the Origin the guard checks. A denied/used ticket cannot be reused. Authorization
  codes expire after two minutes and are consumed under a database lock after S256 verification.
- Access tokens last at most one hour. Refresh rotates both tokens. A connection ends 30 days after
  its last successful refresh (sliding, since 2026-11-09): one in use lives on, one left unused for 30
  days ends and its refresh is refused; an ended connection is never revived. Refreshing does not
  extend the underlying login session, and the connection still ends with it.
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
