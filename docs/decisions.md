# Decision Log

Settled product and technical decisions, each with a short reason, so every person and every
coding agent working on this repo knows why things are the way they are.

How to use: add a new decision as a new entry at the top, with its date. Never edit an old entry.
If a new decision replaces an old one, say so in the new entry. Agents read this file before
starting a new round of work and never silently reverse a logged decision (see
[AGENTS.md](../AGENTS.md)).

The entries dated 2026-10-31 were recorded retroactively: the decisions were already in effect
in the MVP and described across `docs/`; this log gathers them in one place.

## 2026-11-07 — Scripts are written by the member's own Claude through MCP with the group's prompt, by default

Asked by tuananh219ln: write scripts with a Claude subscription instead of the API key, the team being two people.
Running the subscription inside the app stays refused ("Claude connects through the MCP server on each member's own
plan", below). Instead the MCP server hands the member's Claude the exact prompt a script job would send
(`get_script_prompt`: the group's prompt, banned words, photo hint, fixed output format) and saves the JSON it writes
with the job's own parser and `save_script` (`create_video_from_group_prompt`), so such a video has everything an
API-written one has; the prompt is built by the job's own `jobs.script_prompt`, so the two cannot drift. "Tạo
video"'s options come along: a 30-day plan idea (`list_plan_ideas`, `plan_item_id`: its pain and hook in the prompt,
the video linked to it), "AI gợi ý hiệu ứng" (`ai_effects`) and "Video xuyên suốt". The server's instructions make this the default and keep `create_video` (the team's API, paid)
for when the member asks for it. Such videos are marked `videos.written_via = "assistant"` (migration 0056) and the
video page says "Kịch bản viết bởi Claude của thành viên qua kết nối MCP", next to the API's "Kịch bản viết bởi
<provider · model>", so the team sees which one wrote each script. The "Tạo video" button in the app still uses the
API key.

## 2026-11-07 — "Edit từ footage": a member's footage cut by its words; a clip may keep its own sound

Asked by tuananh219ln after reading AIEV (github.com/notivn/AIEVv2), whose core is "put footage in, the AI cuts it
and captions it": the team works together, without one owner deciding, and asked to start. Planned in three parts;
this is the first:

1. **Footage cut by what is said** (this entry): a fifth way of "Từ video mẫu", `footage`, takes the member's own
   footage (the sample's link or upload and its limits: 100 MB, 3 minutes) and makes the scenes with no LLM call
   ([footage.py](../api/src/reels_api/footage.py)): ElevenLabs Speech-to-Text's words, each with its seconds (now
   kept as `video_references.words`, migration 0055), split at pauses of 0.45 s and at fillers, each stretch one
   scene of at most 10 s, the first 90 s kept, as a jump cut. The words are required here, unlike for a sample
   (2026-11-05, 2026-11-07): without them the job fails with the reason (no key, or the key's missing
   `speech_to_text` permission), since there is nothing to cut by.
2. Next: the AI chooses the hook, the on-screen text, effects and b-roll from "Kho tư liệu".
3. Then: a long video cut into several shorts, scored by the AI (AIEV's "Auto cut").

This changes two logged rules, on purpose:

- **"A clip's own sound stays out of the render"** (2026-11-01, and the render core's "the clip's sound is never
  used") now holds unless the scene's `video_sound` ("Tiếng gốc") is on. The render core takes the clip's audio,
  in step with its picture (half a crossfade in when the clip leads its scene), at its speed, onto the narration's
  track, so the music ducks under it and QC expects sound. Off, the filter graph is the one it always was. Any
  clip scene can turn it on in "Cắt video" when its clip has sound; a new or removed clip turns it off. A render
  machine on older code ignores the field and renders the clip silent, so machines are updated with this.
- **"Captions time each word by an estimate"** (2026-11-01) stays for narration; a clip with known words
  (`scenes.words`) is captioned at those words' real seconds.

A footage video is marked hand-written (no AI wrote its words, so none reviewed them), has narration off, hard
cuts, word captions and ducking. A person watches a sample MP4 before this is called done, as for any render change.

Merged after "Kiểu video" (same day): the migration is 0055, and over a backdrop ("Video xuyên suốt") the backdrop
stays silent, so a scene's "Tiếng gốc" and clip words are not used there.

## 2026-11-07 — "Kiểu video": slides or one backdrop ("Video xuyên suốt") with "Ảnh món" photo layers

Asked by tuananh219ln from a spec written without the code ("Đặc tả code: 3 dạng video Reels", by Looper), who then
left every open choice to the agent ("bạn tự quyết đi, code luôn"). Built on what exists instead of the spec's own
model:

- **Two modes, not three.** `videos.mode` is `slides` (as before) or `single`. The spec's third mode
  (`single_overlay`) is `single` with a photo layer on the scenes that name a dish, so nothing has to be hidden
  when switching between the two.
- **The backdrop is the title scene's photo or clip**, not a new `masterMedia` field: every way of choosing a
  picture (upload, stock, library, AI, a pasted link, crop, clip start and speed) already works on it, and the
  first frame stays the cover, as before.
- **"Ảnh món" is a photo layer** (`scene_layers.kind = "photo"`) showing its scene's own photo, not a JSON
  `scene.overlay`: the studio's layers already have their place, seconds, entrance, drag and undo. Its frame and
  width are named presets (three widths instead of the spec's 25–80% slider), keeping "never free size sliders"
  (2026-11-01, 2026-11-05); the place stays free, as for text boxes. One per scene for now; more is a later step.
  A product photo already cut out is supported (frame "Giữ nguyên"), as members find such photos (2026-11-07).
- **The pause after narration** (0.4 / 0.7 / 1 s) is a video option for every video, with 0.4 s, today's pause,
  the default, so no existing video changes; it sets the seconds of scenes that follow their narration and leaves
  the render as it is. Seconds stay editable in every mode ("Tự khớp lời đọc" already follows the narration).
- **Joins and loops:** hard cuts and text fades over a backdrop; a short clip loops with a plain cut at its seam;
  a photo's motion runs once over the whole video.
- **No flag:** the app has no feature flags, and the default (`slides`) changes nothing. A render machine on older
  code refuses a backdrop video (the option is unknown to it) rather than rendering it wrong, and keeps rendering
  slide videos.
- **The AI is not called again** when its answer breaks the mode's rules (the spec's retry): every call costs, and a
  stray keyword only adds a photo layer a member can turn off.

Not built from the spec: the "Để AI chọn" mode, a timeline lane per layer type, a per-platform safe zone for the
photo (the studio's existing zone applies), "Hiện từ giây N" on the card (the studio's layer start does it).
A person watches a sample MP4 of each mode before this is called done, as for any render change.

## 2026-11-07 — An /api endpoint the browser visits never answers with a redirect

Found on production right after the TikTok connection shipped: "Kết nối TikTok" stopped on
`/api/tiktok/oauth/start`, and TikTok's way back ended in a 404. The web's `/api` proxy on Cloudflare Workers follows
a 3xx itself, on the api's side, instead of handing it to the browser (`next dev` hands it over, so local runs and
E2E did not show it). So an endpoint a browser opens answers with data or a page, never a 3xx: "Kết nối TikTok" asks
the api for TikTok's address and the page goes there itself, and the OAuth callback answers with a small page that
sends the browser back to Tài khoản affiliate. The Redirect URI registered with TikTok is unchanged.

## 2026-11-07 — TikTok through its API: each member connects their own account; a draft is the default

Issue #46, brief [docs/specs/tiktok-posting/brief.md](specs/tiktok-posting/brief.md). The TikTok developer app
"Reels Studio" (Login Kit + Content Posting API, scopes `user.info.basic`, `video.upload`, `video.publish`) is set up;
its review needs a demo of the real integration, which this builds. Posting by hand ("Đã đăng tay") stays as it is.

- **OAuth per member, the tokens are each member's own:** the tool is shared, the money is each member's (2026-10-31),
  so a member connects and posts only their own TikTok accounts. One TikTok account (`open_id`) belongs to one member:
  connecting one another member already connected is refused, never taken over. The unit owned is still the
  Publication (video × platform × account).
- **The connection hangs on the member's TikTok `AffiliateAccount`** (new table `tiktok_connections`), found by the
  profile's username or made from it, so posting by hand and through the API share one idea of "the member's TikTok
  account"; a Publication still names `affiliate_account_id`.
- **A draft (`video.upload`, to the member's TikTok inbox) is the default; posting directly (`video.publish`) is the
  option.** Until TikTok audits the app, a direct post is private only (`SELF_ONLY`, private accounts, 5 users a day),
  and TikTok Shop's cart can only be attached in TikTok's app: the draft is the route that works for real today.
- **A direct post always says `is_aigc = true`:** every video of the app is made with AI; TikTok asks for the label and
  does not hold labelled posts back.
- **No TikTok numbers in the app this round** (no `video.list` scope): TikTok's views are still noted by hand, and
  `metrics.py` keeps leaving TikTok posts alone. TikTok's API gives no link to the post, so the member who sent it pastes
  the link afterwards. No cart through the API (TikTok has none).
- **The app's Client Key and Secret are in `.env`** (`TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`): they are the app's
  identity, not a member's, unlike the keys members paste on the Cài đặt pages. The Sandbox's own pair goes in the same
  two variables while the demo is recorded.
- **Not posted twice:** TikTok's `publish_id` is saved before the upload, and "Thử lại" first asks TikTok about that
  post; a new one is started only when TikTok holds no finished upload of it. A rate limit fails the job, never a retry
  loop. A post that never reached TikTok (its job failed before the upload) is replaced by the next "Đăng lên TikTok".

## 2026-11-07 — "Từ video mẫu" learns from the stills when ElevenLabs will not write the words down

Found by a member (namtc): every "Từ video mẫu" failed, pasted link or upload, with "Key ElevenLabs không hợp lệ",
because the team's ElevenLabs key was made without the `speech_to_text` permission (it narrates fine). The words of a
sample were always optional (2026-11-05: "A silent sample, or no ElevenLabs key, works from the stills alone"), so a
refusal now counts as no key: a key missing the permission, no quota left or an outage leaves the words empty, is
logged, and the job goes on from the stills. A key missing the permission is named as such in the log. To have the
words back, turn on Speech to Text for the key on ElevenLabs.
## 2026-11-07 — Renders and motion scenes run on a member's own computer; the VPS prepares and keeps the data

Asked by tuananh219ln: the VPS is small, and his computer (i7-8700, 32 GB, GTX 1060) is far stronger. Chosen with
him: a "render machine" ([render_nodes.py](../api/src/reels_api/render_nodes.py)) rather than moving the whole app to
his computer, which would lose the shared library and need it on all day for scheduled posts. The VPS still runs the
web, the database, storage, posting and every light step of a job; with the switch on, a render or motion job is
packed and **waits for a machine** (his choice over a VPS fallback), shown as "Đang chờ máy render" and cancellable.
A machine reaches only `/api/node/...` with its own token, stored hashed and revoked by deleting it; it never gets
database or storage access. The worker's "a running job after a restart failed" rule (2026-10-31) now skips jobs
handed to a machine, which live on without it. Rendering on the GPU (NVENC) is not part of this: the CPU renders a
30-second video in under a minute on that computer, and an encoder change is a render-core change to be watched
first. The Claude chat on the video page through his own subscription, run by the same computer, is the next step.

## 2026-11-07 — An article's AI writes its own doctor reminder; articles get a pinned comment and Shopee suggestions

Asked by a member (namtc) after using "Bài viết": the fixed line "Tham khảo, không thay thế tư vấn bác sĩ." the app
added under every caption read as machine-made. This changes "The disclaimer line is added by the app, never left to
the AI" of the 2026-11-06 entry on articles: the AI now writes one short reminder in the post's own voice when the
post is about health (who should ask a doctor first), or none; the app adds nothing of its own and no longer warns
about a missing sentence. That fixed disclaimer was still "deferred" for videos (docs/content.md), so nothing about
videos changes.

Asked at the same time: an article now has what a video's "Nội dung đăng" has for its comment.
- **A pinned comment**, written by the AI with the caption and editable: the comment the worker writes under the post
  opens with it, then the products' links; a post with a pinned comment and no product still gets the comment. A
  change edits a comment already written. A link in it blocks posting, as in the caption.
- **Product ideas and Shopee's suggestions**, as on a video: the AI writes up to 3 ideas; the worker searches Shopee
  for them with the writer's own account after "AI viết", or on "Tìm sản phẩm"; "Chọn" approves a product meeting the
  rules and attaches it, at most two per article; a pasted Shopee link is listed too. `affiliate_suggestions` rows
  now belong to a video or an article (migration 0051). The web's suggestion block is one component for both.

## 2026-11-07 — "Kho tư liệu": the team's photos and clips by folder and from pasted links; Remotion stays out

Asked by tuananh219ln: inputs from a folder, combined with Google photos and TikTok clips, where the Google and TikTok
buttons open a search for the product being made and pasting the link back brings the photo or clip in. The library
is the team's (`media_items`, migration 0050), uploaded one file per request with its folder, links downloaded with
the rules of a link pasted on a scene; using an item copies it into the scene, as "Đã dùng trong nhóm" does
(2026-11-05). The app still never searches Google or downloads from it by itself ("Shopee through its API, never by
scraping", 2026-11-03): the buttons only open the member's browser on the search, and the member picks and pastes.
The assistant chooses by looking at items (`view_media`), for the quality bar of the entries below.

Remotion was asked for again, for personal use; the member agreed to drop it unless it does more than HyperFrames and
FFmpeg, and here it does not: HyperFrames makes the motion graphics and FFmpeg cuts, joins and exports. "No Remotion"
(2026-10-31) stands.

## 2026-11-07 — Every render gets automatic QC against the platforms' delivery specs

Asked by tuananh219ln for a high bar on the finished video, after AIEV's QC (`qc.ts`): the render job measures the
MP4 it made (format, length, EBU R128 loudness against −14 LUFS, true peak against −1 dBTP, black frames, frozen
pictures, dead air) and keeps the result with the MP4. It advises and never blocks: a failed check does not fail the
render or stop posting, because a member may have a reason (a deliberate black beat), but the MCP assistant must fix
failed checks before it calls a video done. Making the render itself aim at −14 LUFS (loudness normalisation in the
render core) is a separate change, to decide once QC shows how far today's renders are from it.

## 2026-11-07 — The assistant edits like the studio and checks its own frames; the finished video's bar is high

Asked by tuananh219ln: finish "edit video with a Claude subscription", following AIEV, with "Tiêu chuẩn video thành
phẩm phải rất cao". The MCP server gains the studio's editing (scene effects, order, split, delete, text and sticker
layers, sound effects, music and narration settings) through the same handlers, presets and locks, so the assistant
can do nothing a member cannot do on the video page and every look stays a named preset (2026-11-01). Like AIEV,
whose agent verifies every frame before a final, the assistant can look at a scene's preview and at frames of the
rendered MP4, and the server's instructions make that loop mandatory: plan, build, look at every scene, render, look
at the MP4, fix, and only then report done. A person still watches the MP4 before a render change is called done.

## 2026-11-07 — "Cảnh động": Claude writes a scene in HTML + GSAP, HyperFrames renders it into the scene's clip

Approved by tuananh219ln on issue #120 ("tôi duyệt làm luôn"), for nicer affiliate product videos. Changes, for one
kind of scene, "Every look stays a named preset" (2026-11-01): a motion scene's look is whatever the assistant
writes. Keeps "Rendering is a native FFmpeg filter graph; no MoviePy, no Remotion" (2026-10-31) and "the render
core stays FFmpeg" (2026-11-05): HyperFrames only makes one scene's clip, and FFmpeg makes the video from it like any
clip; Remotion is still not used (paid licence for this team).

- **Written through MCP on the member's own Claude** (`set_scene_motion`), so it costs nothing to the team's AI
  service; there is no editor for it in the app. The scene card says "Cảnh động · N giây"; any other photo or clip
  replaces it.
- **Untrusted markup, checked and cut off from the network:** document and embedding tags, external scripts and
  URLs, network, storage, timer and `eval` APIs, the clock and `Math.random` are refused before it is stored; the
  worker's Chrome runs through a wrapper whose `--proxy-server` reaches nothing, so only HyperFrames' loopback file
  server answers.
- **The worker image grows** by Node 22, HyperFrames 0.9.19, GSAP 3.15.0 and HyperFrames' headless Chrome (a few
  hundred MB), pinned; the build renders a short scene so a broken Chrome never deploys.
- **A person watches it:** as for any change to what the render shows, a sample MP4 with a motion scene is watched
  before this is called done.

## 2026-11-07 — Claude connects through the MCP server on each member's own plan, and makes product videos there

Asked by a member (tuananh219ln), after reading AIEV (github.com/notivn/AIEVv2): edit and make affiliate product
videos for Shopee and TikTok with a Claude subscription. AIEV runs Claude Code headless (Claude Agent SDK) on the
user's own machine with their subscription. Doing that in the worker would put one member's Pro/Max plan behind
a server the whole team uses, which Anthropic's terms do not allow for a third party's product and which shares
an account; it would also add Node and the Agent SDK to the worker. Chosen instead:

- **Claude calls Reels Studio, not the reverse.** The existing private MCP server ("ChatGPT connection",
  `docs/chatgpt.md`) now also accepts Claude's hosted apps (`https://claude.ai/api/mcp/auth_callback`, and the
  `claude.com` one it may move to) and Claude Code's loopback callback on any port. Each member connects their own
  Claude account; the server never holds a subscription. The OAuth rules stay (DCR, public clients, S256 PKCE,
  hashed tokens, 30 days); a grant now keeps the callback it was asked for (migration 0047) because Claude Code's
  port changes every session, and the consent screen names the app and the callback's host.
- **Product videos with no cost to the team's AI service:** Claude writes the script itself and makes a
  "Tự viết" video (`create_video_from_script`), reads the team's affiliate products, gives scenes a TikTok clip
  or a photo from a link through the same download as pasting it on the video page, picks the clip's part,
  attaches approved products and queues the render. Narration and render keep their usual services and costs.
- **Sources as agreed:** TikTok clips and a member's own footage (uploaded on the video page: MCP carries no
  files) as today. Photos found on Google are picked and pasted by a member; the app never searches or downloads
  from Google by itself, like "Shopee through its API, never by scraping" (2026-11-03). The app does not
  remove backgrounds: members find product photos that are already transparent.
- **The render stays FFmpeg.** "Rendering is a native FFmpeg filter graph; no MoviePy, no Remotion" (2026-10-31)
  and "the render core stays FFmpeg" (2026-11-05) are unchanged: Remotion still needs a paid licence for this
  team. Scenes animated with HyperFrames (Apache-2.0, HTML + GSAP rendered to a clip that FFmpeg then places)
  were asked for and are proposed in an issue for the owner (namtc07) to decide; nothing here depends on them.

## 2026-11-06 — Articles are posted as `publications` and measured by reach at 48 hours

Parts 2 and 3 of docs/specs/bai-viet/brief.md, asked by a member (namtc), on the branch of the entry below.

- **An article's post is a `publications` row** with `article_id` instead of `video_id` (exactly one is set), and its
  numbers are `post_metrics` rows, rather than tables of its own: the publish, unpublish and check jobs, the
  affiliate comment, the visitors' comments on "Bình luận" and the 48-hour reading all work for it as for a reel.
  What lists every post and reads its video ("Bài đăng", a Page's dashboard, the reels' medians) keeps to video posts.
- **Never posted twice**, as a reel (2026-10-31): the text sent is stamped on the post before Facebook is asked; a
  retry reads the post Facebook gave back, or, when that answer was lost, looks for the same text on the Page's feed
  and scheduled posts, and posts again only after 30 minutes without finding it, as a reel's upload does.
- **The same caption never goes twice on one Page** (compared without accents, case, hashtags or extra spaces); on
  another Page, or within two hours of a reel scheduled on the same Page, "Đăng" asks first.
- **Reach is an article's main number**: Post Insights' `post_total_media_view_unique`, which Meta's v25 changelog
  names in place of the retired `post_impressions_unique`; if Facebook refuses it, only reach is left empty. Shares,
  comments and reactions come from the post's own fields. The KPI is the team's 0.2 %, as share/reach, read only from
  a reach of 50: below that one share is several percent. Each Page's median is of its articles only (60 days, from 5
  measured), and an article is drawn bold from 10× it, never flagged (2026-11-03).
- **Products**: at most two approved Shopee products, whose links go in the comment the worker writes, never in the
  caption; the caption then ends with "Link sản phẩm mình để ở bình luận ghim.". An article's link carries the sub id
  `bv<article>`, so an order is never taken for the video with the same number; orders are not yet shown by article.
- **"Làm reel từ bài này"** makes a video draft on the article's topic through the usual "Tạo video" (its script job).
- Left for later: an AI picture for an article, articles in "Bài đăng", a Page's queue or its dashboard, and orders
  by article.

## 2026-11-06 — Photo and text posts ("Bài viết") are built, with no stock photos; banned words still only warn

Asked by a member (namtc), from docs/specs/bai-viet/brief.md. This reverses "photo and text posts
(`pages_manage_posts`) wait" in the 2026-11-03 entry on "Bình luận" (and the same reason in the entry on token
checks): an article is a cheap test of a topic before a reel is made, keeps a Page posting and gathers comments. The
risk named then was "unoriginal content" with stock photos, so an article never takes one: its picture is a "Thẻ chữ"
(the caption's first line on a colour, drawn by the api in the app's font), a photo from a pasted link (the link is
kept, the member answers for it, as for TikTok clips), later an AI picture, or none, a text post being valid.

- **"Banned words warn, they never block" (2026-10-31) holds for articles too**, on the brief's default: a banned word
  in the caption is a yellow warning. A link in the caption is different: it breaks the rule that affiliate links go
  only in the pinned comment, so it will block posting.
- **Named "article" in code** (`articles`, `/api/articles`, `/articles`), because "post" already means a
  `publications` row ("Bài đăng"); the menu says "Bài viết", its own item beside "Video".
- **The caption prompt is app data and its format is code**, as for scripts: "Prompt viết bài" per group on
  `/knowledge`, the shape of the answer in `articles.output_format`, assembled by the same `claude._assemble` (which
  now takes the format and what the banned words apply to). The disclaimer line is added by the app, never left to
  the AI.
- **Built in three parts**: drafts first; posting (with "never posted twice"), taking down and the affiliate comment
  next, then the 48-hour numbers (the entry above). Articles do not go into "Bài đăng" or a Page's queue yet.

## 2026-11-06 — "Bài đăng" suggests cloning in one card, the button picks TikTok or another Page

Asked by a member (namtc): "Nên làm bản TikTok" and "Nhân bản cho Page khác" listed the same winners twice. They are
now one "Nhân bản" card beside "Sẵn sàng đăng", each video once with what it still lacks, and a "Nhân bản ▾" button
whose menu offers only what is left: "Bản TikTok" and/or "Bản cho Page khác". This changes only the display of the
2026-11-03 entry ""Bài đăng" no longer suggests posting a video to another Page": the same "did well" reading, the
same rules for each kind of clone, never the same MP4 on a second Page, and one LLM call only when the member confirms.

Same request: on `/videos` a Facebook video's card carried only its version's "TikTok · …" link, so it read as if
TikTok were its only platform. Every card, row and video page now says "Facebook" or "TikTok" beside the status.

## 2026-11-06 — A public privacy page at /privacy, so the Meta app can go Live

The "ALSK Page Manager" Meta app was in Development mode, so the reels it published were seen only by people with a
role in the app: other viewers saw nothing and the 48-hour mark stayed at about 1 view. Going Live needs a privacy
policy URL, so the web app has a public page at `/privacy` (https://reels.quangdang.xyz/privacy once deployed), in
Vietnamese, and the login proxy leaves exactly that path open, as it does `/login`. It is static and calls no API.
It says what the app really keeps and sends: visitors' comments are kept with the commenter's name, members are
disabled rather than deleted (2026-10-31), a Page's token goes with the Page, and each service gets only what its
feature needs. Questions and deletion requests go to the Page by message, the one contact a visitor surely has; a
team email can be added later. When what the app keeps or sends changes, the page changes with it.

## 2026-11-06 — A public terms page at /terms, beside /privacy

The Meta app's settings take a terms of service URL next to the privacy policy, so the web app has a public page at
`/terms` (https://reels.quangdang.xyz/terms once deployed), built like `/privacy`: Vietnamese, static, no API call,
and the login proxy leaves exactly that path open. It says who may sign in (no self-signup), that what is posted
must follow Meta's, TikTok's and Shopee's rules and is the poster's responsibility (banned words only warn,
2026-10-31), that uploaders must hold the rights to their media, and links to `/privacy` for what is sent where.
Contact goes to the Page by message, as on `/privacy`.

The TikTok developer app verifies the domain with a file served at its root, so
`web/public/tiktokBrAExctM9frGJD6lQkMHTFS9wAUMuami.txt` is kept byte for byte as TikTok issued it (the login proxy
already skips files with an extension). Delete it only if the TikTok app is removed. It replaced the first file,
`tiktokthafjQKP8W43JYUm5iG01Gsy3j5KIHeD.txt`, on 2026-11-07, when TikTok issued a new one.

## 2026-11-06 — A reel deleted on Facebook is known by the 400 (#100) Facebook answers, while the Page still reads

Reels deleted in Meta Business Suite could be neither checked nor deleted in the app: "Kiểm tra" and "Xóa" failed
with "Không đọc được trạng thái reel… Facebook không cho token này truy cập Page", and the post stayed "Đã đăng".
The app took only an HTTP 404 for a reel Facebook no longer has, but Facebook answers 400, code 100, subcode 33,
the same as for a reel the token may not read. Now that answer means the reel is gone only when the same token still
reads the Page (`GET /{page-id}`); otherwise it stays unknown and nothing changes, so a token that lost the Page
never closes a post or posts it again. It applies to the status read ("Kiểm tra", "Xóa", "Thử lại") and to the
delete. The test fake now answers a lost reel as Facebook does.

## 2026-11-06 — "Bài đăng"'s filters move onto the list they filter

On the owner's call ("làm lại UI filter"). The search, status tabs, sort and Fanpage filter sat under the title, in
one wrapping row with the tabs in the middle and the Fanpage filter alone on a second line, above the KPIs and the
suggestions, which they never filtered. They now sit on the list's own card: the status tabs across its top, then
"Tìm theo tiêu đề", "Mọi Fanpage" and "Sắp xếp" at the right, the general toolbar order. The page is the one
exception to "search and filters on one row under the title" (ux-guidelines), because its title is followed by
blocks the filters do not touch. Nothing else changes: the same tabs, counts, filters and sort.

## 2026-11-06 — A deleted or cancelled post's numbers are history: no median, no KPI, no total

Four reels on one Page, posted through the API on 3–5 November, were hidden from other viewers by Facebook (posted
by hand, the same content showed). Their ~1 view at 48 hours measured that fault, not the content, yet pulled the
Page's median down, so later videos looked many times above it, and counted in the weekly KPIs. A deleted reel's
last reading also stayed bold and was added to "Tổng view". Now a post whose status is `deleted` or `cancelled`
feeds no Page median and no weekly KPI, its views add nothing to "Tổng view" and sort last, and its last reading is
shown as "Lúc xóa: N view (đo lúc …)". Its `48h` and `latest` rows are kept as history and still shown with it.
Unchanged: the 48-hour mark is written once and never again, live and scheduled posts are read as before, and
"Cập nhật view" stays on live posts only. A post still on Facebook but hidden by it is not left out by this: it
has to be deleted first (spec: docs/specs/metrics-deleted-posts/brief.md).

## 2026-11-05 — A Page's dashboard gets a "Nội dung" tab, one row per post, from the numbers the app already reads

Phase 2 of the entry below, asked by a member (namtc): "Nội dung" on `/fanpages/[id]`, like Facebook's content
library, lists every post the app made to the Page that went live in the dashboard's period, with the latest reading
of each and its 48-hour views against the Page's median (`GET /api/fanpages/{id}/content`).

- **Still only what the app has**: no new Facebook call, table or migration; posts made outside the app are not
  there, and the tab says so. A reel taken down after going live stays, as "Đã gỡ", since its numbers were real.
- **Sorting, the "Cột" choice and the CSV file are the browser's**, from the rows it already has: the file is what
  the table shows, in its order and columns, rather than a second export on the api (unlike the products' "Xuất
  CSV", which exports a filtered list the page does not hold). The chosen columns are remembered per browser, like
  the list or grid choice, not per member.
- **"Cập nhật view" is the same request as on "Bài đăng"** (`POST /api/posts/{id}/metrics`): it asks the worker,
  never Facebook directly.
- **"Bài đăng" stays grouped by video** (2026-11-03): the per-post view is per Page, here. More Page Insights
  metrics remain a later phase.

## 2026-11-05 — Each Page gets a dashboard like Facebook's, from the numbers the app already reads

Asked by a member (namtc), who approved the design: with about 25 Pages in the team, a card's four 7-day numbers
and the "Số liệu 30 ngày" table did not show how a Page was doing. A click on a Page's card on "Quản lý Page" opens
`/fanpages/[id]`, modelled on Facebook's Professional Dashboard: one period for every tab (7, 28 or 90 days in
Vietnam time, today included), each figure with its ↑/↓ against the same number of days just before, and tabs
Tổng quan, Lượt xem, Tương tác, Đối tượng and Lịch đăng (`GET /api/fanpages/{id}/dashboard`). The "Số liệu 30 ngày"
dialog goes; its table is under each chart ("Xem bảng").

- **Only what the app already has**: `fanpage_insights`, `fanpage_followers` and the posts' `post_metrics`; no new
  Facebook call, table or migration. Numbers Facebook does not give the app (followers against non-followers, content
  types, traffic sources, unfollows, 3-second and 1-minute views) are left out rather than estimated.
- **Reactions, comments, shares and the average watch time are the app's posts' numbers**, summed from each post's
  latest reading for the posts that went live in the period; Page Insights has only the engagements total. A post's
  numbers keep growing after its day and posts made outside the app are missing, so the tiles say they are
  approximate.
- **The posting queue moves to the Page's "Lịch đăng" tab**, changing "Everything about a Page sits on its card" of
  the entry below: the card keeps one line (group, times, "N video trong hàng chờ"). The queue rules are unchanged.
- **"Bài đăng" stays grouped by video** (2026-11-03); a per-post content tab on the Page ("Nội dung", like Facebook's
  content library) and more Page Insights metrics are later phases, not built here.

## 2026-11-05 — Each Page has a posting queue, filled by the worker at the Page's posting times

Asked by a member (namtc): with 5 Pages each, scheduling every video by hand did not scale. Each Page posts one topic
group (`fanpages.knowledge_topic_id`, migration 0044) at its own posting times or, by default, at the group's
(2026-11-04, "posting times"). "Thêm vào hàng chờ" on a rendered video puts it in the queue of the member's own Page
of the video's group; it is pressed by hand, after watching the MP4, so a video with a wrong text or a weak picture
never goes out unseen. Videos going into the queue by themselves once rendered were left for later (issue #108).

Once a minute the worker gives each healthy Page with a queue at most one post: the first video that can go, at the
next free posting time within 48 hours. It makes the same pending post and `publish` job as "Đăng" with "Hẹn giờ",
so "Scheduling uses Facebook's own scheduling" (2026-10-31) still holds: the worker only chooses the time, and
Facebook publishes. It is the first time the worker starts a post a member did not press "Đăng" for; the member who
queued the video is recorded as the post's author. 48 hours only, since Facebook keeps the MP4 sent with a scheduled
reel and a later edit would not reach it. A video that cannot go stays in the queue with why, and the next one goes.
Only the Page's owner sets its group and times and reorders its queue, as for its Shopee account (2026-11-03).
The queue is moved with "Lên"/"Xuống" rather than dragging.

Everything about a Page sits on its card: "Kết nối Fanpage" becomes **"Quản lý Page"**, its own menu item under
"Video", out of the Cài đặt group, on the member's choice over a separate "Hàng chờ" page. This is the "Quản lý Page"
menu the 2026-11-03 entry on token checks kept for when there was more to show; its address stays `/fanpages`.

## 2026-11-05 — "Từ video mẫu": a script learned from a sample video, with clips cut from it, in one of four ways

Asked by a member (namtc): paste a link or upload a video, and have the AI analyse it and write a script, make the
video and pick its pictures. Choices, as agreed with the member:

- **The AI sees stills and words, not the video.** The worker takes up to 16 stills and sends them as images with
  the sample's words, written down by ElevenLabs Speech-to-Text (`scribe_v2`, the narration's key; no new
  provider). A silent sample, or no ElevenLabs key, works from the stills alone.
- **Scenes show the sample itself.** The member preferred the sample's own pictures to stock photos, and chose the
  stronger option of a clip over a still: the AI names a stretch of the sample per scene (2–10 s) and the job cuts
  it as the scene's clip. A scene without one gets "Tự tìm ảnh" as usual. The risk is the one taken for TikTok
  clips (2026-11-03): the member who brings the sample is responsible for it; the prompts still ask for new words,
  never copied or translated sentences.
- **Four ways, chosen in the dialog, each described there:** "Nhanh" (one call sees the stills and writes the
  analysis and the script, the cheapest and the best at picking clips), "Hai bước tự động" (analysis with the
  stills, then writing from the analysis without them), "Duyệt phân tích trước" (the member edits the analysis,
  then "Viết kịch bản") and "Dùng mẫu đã học" (another video from a sample already analysed, no new download or
  analysis).
- **A sample is kept until someone deletes it** (`video_references`), for clips and for "Dùng mẫu đã học"; videos
  made from it keep their own clips when it goes.
- **Sources:** a TikTok or YouTube (Shorts) link through yt-dlp, a video file's link, or an upload; 100 MB and
  3 minutes at most. Facebook and Instagram Reels are left out (yt-dlp is often asked to log in there): download
  the video and upload it. A scene's pasted link stays TikTok-only.
- **Prompts are app data** ("Prompt text is app data", 2026-10-31): "Prompt học từ video mẫu" and "Prompt phân
  tích video mẫu" per group on `/knowledge`, empty meaning the defaults; the clip stretches and the analysis
  fields are part of the output format, in code.
- **Long work in the job queue:** the request only stores the link or file; download, stills, words and LLM calls
  run in the `learn` job. The migration is 0043, after `feature/studio-editor`'s 0037–0042.

## 2026-11-05 — "Xem trước" grows into a studio with tracks, one phase at a time; the render core stays FFmpeg

Asked by a member (namtc), from CapCut's editor: more editing in the preview, with effects. Chosen over a free
timeline (clips, text and sound anywhere on any track, independent of the scenes), which would rewrite the data
model and the render core: the scene stays the backbone and tracks are added around it, in phases, all on one
branch (`feature/studio-editor`, the member's choice):

1. Tracks and tools on what exists (this entry): "Chữ", "Giọng", "Phụ đề" and "Nhạc" under the scenes, padlocks on
   "Cảnh" and "Chữ" (each member's own, in the browser), and "Tách cảnh" at the playhead (S), which the api does as
   `POST /scenes/{id}/split`: the rest of the scene becomes a silent scene with its own copy of the picture.
2. Per-scene transitions, colour presets and clip speed in the render.
3. Text and sticker layers with their own times and entrance effects.
4. Sound effects and music sections.
5. Comments at a second sent to the AI, and "AI tại mốc" (a picture or a line of text made for that second).

Every look stays a named preset (2026-11-01: "never free colour or size sliders"); each effect is written twice,
for FFmpeg and for the preview's CSS, and a phase that changes the render is done only when a person has watched a
sample MP4. AIEV (github.com/notivn/AIEVv2, MIT) was read for reference: its colour presets (FFmpeg filter chains)
and transition curves may be adapted with its notice kept; its Remotion engine (paid above 3 people) and its sound
effects (no licence records) are not used. The drawer keeps its size (2026-11-05 above): a full-screen studio was
considered and left to the owner.

Then, on the member's choice, a "Chỉnh cảnh N" panel beside the phone holds the scene's content too (text,
narration, photo or clip and how to find one, search terms), so a scene is made without leaving the studio. It uses
the scene card's own field components, so nothing is built twice and the video page keeps every field: removing
the duplicated fields from the cards (seconds, clip start, text place) was considered and dropped, since the page
stays the place to work on a phone and where "Render" points at what blocks it. Effects from phase 2 on live only
in the studio.

Phase 2: each content scene may set its own transition in (12 named, FFmpeg's `xfade`) and a colour preset (14
named, adapted from AIEV's); the video's transition stays the default, and the title scene gets neither, so the
first frame stays the cover the api draws without them. A cut among transitions is a one-frame fade at the
crossfade's offset rather than a different timeline, so the video's length and every narration stay where they
were. The part after "Tách cảnh" cuts in.

Phase 3: text and sticker layers, each its own row (`scene_layers`) saved on its own like the scene fields, so the
"one block with a version" idea above was not needed. Stickers are shapes the render core draws (no image files,
so nothing to license); text, styles, sizes and entrances are named presets. The api draws a layer's picture with
the render core, so the phone shows what the MP4 lays on. The title scene takes none, as for the effects.

Phase 4: sound effects are made by FFmpeg's own source filters, not downloaded, for the same reason as the
stickers (AIEV's bundled sounds have no licence records, and a laugh or a voice cannot be made this way, so there is
none). Music is still one song per video; instead of several songs, a scene can set its own music level and the
video where the song starts. Several songs in one video are left until the team asks for them.

Phase 5: "Góp ý" and "AI tại mốc" are one flow. A note is a comment at a second, kept for teammates as well as
the AI; "Nhờ AI sửa" sends every open note to one `revise` job (asked first: one AI call), which may change the
scenes' text and narration and add text layers at a second, and answers each note. It goes through the job queue
like every LLM call, its prompt words are app data per group ("Prompt sửa theo góp ý"), and the notes are fenced in
the prompt as the members' words. A separate "AI writes one line here" button was dropped as the same thing as a
note asking for it. AI pictures for a scene stay the existing "Tạo ảnh AI".

Automatic effects, on the member's choice (all three): "Tự dựng" puts a template on a video by fixed rules (no AI),
"Gợi ý của app" being the app's own template; the team saves its own templates from a video it likes and may pick
one for every new video (none by default, so nothing changes until a member chooses); and "AI gợi ý hiệu ứng" is an
option when making a video with AI. All three use the same named presets and the same apply, and stay changeable
by hand in the studio.

"Cỡ chữ" (Lớn, Vừa, Nhỏ) for the scenes' and the title's text box, from members' feedback that a long title filled
the screen. A preset, as sizes stay presets (2026-11-01). Vừa and Nhỏ scale the font Lớn would pick rather than only
lowering its maximum, since Lớn already shrinks long text and a lower maximum alone changed nothing there. Lớn stays
the default, so existing videos and their MP4s are unchanged until a member picks another size.

## 2026-11-05 — "Xem trước" is laid out like a video editor, in a wider drawer, with a ruler and a playhead

Asked by a member (namtc), from TikTok Studio's editor. The drawer of "The preview opens in a drawer" (2026-11-02)
stays, on the member's choice, so a strip of the page is still in sight; it only grows to the screen's width less
64 px. Inside: a tools column ("Cảnh", "Khung", "Giọng đọc") with its panel, the phone in the middle, the timeline
along the bottom. The timeline gets a ruler in seconds, scene segments showing their picture, a zoom and a playhead
that goes to any second, paused; playing on from there starts the clip, motion, music and ElevenLabs narration at
that point, while the browser's voice, which cannot start mid-sentence, waits for the next scene. No "Lưu"/"Huỷ":
changes still save at once (2026-11-02, "edit mode stays without Lưu/Huỷ"). Splitting a scene at the playhead,
TikTok's "Áp dụng độ mờ" and a full-page editor were left out.

## 2026-11-05 — CI does not test the same code twice

Asked by the owner (namtc07), changing the 2026-11-03 entry's "a push to `main` still runs every job
before it deploys". Each PR ran api pytest three times and E2E twice on the same files: as a draft, when
marked ready, and after the merge. Now marking a PR ready reruns api, worker and web only if they did not
pass on that commit (a draft run cancelled by marking it ready counts as not passed), and a push to
`main` deploys without testing again when its files are exactly the merged PR's last commit and every
check (api, worker, web, the image job, E2E) passed there. The "Protect main" ruleset requires a PR to
be up to date with `main` before merging, so a merge, squash or rebase leaves the tested files; if that
rule is ever turned off, or a push does not come from a merged PR, or GitHub cannot be asked, every job
runs before deploying as before. The 2026-10-31 rule that only CI deploys, after every test passes,
holds: the tests that passed are the ones on those exact files.
## 2026-11-05 — The video list shows a TikTok version on its source's card, and filters by topic group

Asked by a member (namtc): the list showed the Facebook video and its TikTok version as two cards with the same
title. Only the display changes: "A TikTok version is its own video" (2026-11-03) stays, since the two are different
files with different products, states and ways of posting. On `/videos` the version is a small "TikTok · Nháp" /
"TikTok · Đã đăng" link on its source's card or row (`variant_of_id` and `tiktok_posted` on each row); it is listed
on its own when a platform is chosen or its source is filtered out. A Facebook clone for another Page keeps its own
card: it is a real variant, posted to another Page. A "Mọi nhóm chủ đề" filter, remembered in the browser, keeps one
group's videos; it is a filter rather than a section per group, so the newest videos stay at the top.

Three more on the same screen, all worked out in the browser from the list's rows: the group filter counts each
group's videos and, with a group chosen, says what was made this week; a "Cần làm" status (a draft older than 2 days,
a failure, an outdated MP4, or a finished video not out anywhere) to start the day with; and a Facebook card at 3× its
Page's median or more at 48 hours with no TikTok version offers "Tạo bản TikTok". 3×, not the 1× of "Bài đăng"'s
suggestion, so the list nudges only for the clear winners. Showing TikTok's views on the version's link waits for
TikTok's numbers (issue #46).

## 2026-11-05 — Photo search follows the topic group; the group's own pictures can be reused

Asked by the owner (namtc07): with several topic groups (Sức khỏe, Vườn rau tại nhà) the scenes' search
keywords were written as for food, so a gardening scene found cooked dishes.

- **Keywords describe what is in the frame** (a dish, a plant, an object or an action, with its state), not
  only a dish or ingredient. The output format is code, so this applies to every group.
- **"Gợi ý tìm ảnh" per topic group** (`knowledge_topics.photo_hint`, migration 0036): free text added to the
  group's script and clone prompts, before the format, for the keywords and AI image prompts. Empty adds nothing,
  so existing groups write as before until a member fills it in.
- **Google and TikTok open on a keyword the member picks** from the scene's list, not always the first.
- **"Đã dùng trong nhóm"** copies a photo or clip another video of the same group uses into a scene. A copy, not a
  shared file, so deleting either video never breaks the other; a photo keeps its source for a copyright claim.
  Limited to the same group: groups are separate channels' material.

## 2026-11-05 — A Shopee product from an ordinary shop can be approved

Asked by the owner (namtc07): good seed products from "Shop thường" could not be approved. Replaces, for Shopee only,
the shop type rule of "Products per platform" (2026-11-03) and "Affiliate products are approved by fixed rules"
(2026-10-31): any shop type passes. At least 4.7 stars, 100 sales, no banned word and a commission not expired still
apply, and Shopee Mall still ranks first among equal money per order. TikTok Shop's proposed shop rule is unchanged.
Search suggestions now include ordinary shops meeting the other rules.

## 2026-11-05 — An affiliate link can be pasted on the video, with or without an App ID

Asked by namtc07 while the team's Shopee App ID waits for Shopee's approval: getting one product meant downloading
Shopee Affiliate's "Lấy link hàng loạt" file and importing it. Changes one point of "Shopee products are added by
their link or Shopee Affiliate's file" (2026-11-05, below): pasting without an App ID was refused there.

- **"Dán link aff" on the video** (`POST /api/affiliate-products/videos/{id}/links`): each Shopee link becomes a
  product of the video's topic group (one already listed, by its link or item id, is reused) and is listed under
  "Sản phẩm gợi ý từ Shopee" as "Link đã dán", where "Chọn" approves and attaches it as for a search result. A new
  search keeps these rows (`affiliate_suggestions.keyword` = "Link đã dán", no migration).
- **Without an App ID in the team** the draft holds only the link; "Sửa thông tin" opens the product form on the
  video to fill in name, shop, type, stars, sales, price and commission. With one, the worker reads it as before.
- The "Thêm sản phẩm" drawer on /affiliate is unchanged: it still asks for an App ID and points to the file.

## 2026-11-05 — CI takes FFmpeg and Playwright's libraries without the apt mirror; every job has a timeout

The runners' Ubuntu mirror at times downloads at about 57 kB/s: installing FFmpeg took 14–19 minutes on
some shards and Playwright's `--with-deps` 6 more, so one run used about 95 runner minutes instead of
45, and the account reached its spending limit on 2026-11-05. CI now takes ffmpeg and ffprobe from a
static 7.1.1 build (`mwader/static-ffmpeg`, pinned by digest, cached), the version Debian gives the
production images; the render parity test still runs inside the worker image with its own FFmpeg.
Playwright's browsers are cached, and its system libraries are installed only when the runner image
lacks one. Every job has `timeout-minutes`, so a hung step no longer bills up to six hours. The
2026-11-03 entry (four shards each for api and E2E, draft PRs skip E2E) is unchanged; whether to cut
the shards is left until the run times after this change are known.

## 2026-11-05 — Scenes follow their narration; a named scene's voice text opens with its name; edits from the preview

Asked by the owner (namtc07), who agreed to change the 2026-11-03 rule below:

- **"Tự khớp lời đọc"** (`scenes.seconds_auto`): once a scene's narration is made (the voice job, or a render's), its
  seconds become the narration's length plus the pauses around it, shorter or longer than before, within the 1–10 s a
  scene may be set to; a longer narration still lengthens the scene at render as before. Typing the seconds turns it
  off for that scene. It is on for the scenes the app writes (script, clone, "Tự viết", "Thêm cảnh") and off for
  scenes made before, so seconds a member already tuned are kept. The render is unchanged: it reads the seconds the
  voice job set.
- **The name before the narration.** This replaces "the rule itself still does not require the dish name" of
  2026-11-03: a scene whose on-screen text opens with a dish, product or thing opens its voice text with that name and
  a comma. Scenes without one (a mistake, a step) are unchanged. Narration adds the comma itself after a leading name
  with no pause, so older scripts read "Rau muống, ngâm hạt…" too; those scenes' made MP3s are read again once, at the
  next voice job or render.
- **The preview edits** the scene being shown: its seconds, "Tự khớp lời đọc", the clip's part, the text box dragged on
  the phone (kept in the safe zone as the render places it), and the video's ElevenLabs voice, with the same saves as
  the scene cards and "Thiết lập". The phone itself is edited too: text typed in place, the box snapped to the
  middle and warned when an app's buttons or caption would cover it (estimated zones in `preview/coverage.ts`), the
  timeline's edges for seconds and its segments for the order, a trim bar for clips, a toolbar, keys and touch.
  "Hoàn tác" only covers what can be put back through the same calls (text, place, seconds, clip, transition,
  order); adding and removing a scene are asked first instead.

## 2026-11-05 — Shopee products are added by their link or Shopee Affiliate's file, not typed in

Owner's request ("drawer thêm sản phẩm chỉ cần dán link aff, sẽ tự fill các thông tin còn lại, không nên nhập tay").
Follows "Shopee suggestions and links through its API, never by scraping" (2026-11-03) and changes nothing in it.

- **A pasted link** becomes a draft that the worker reads in its next round (`affiliate_rounds.lookup`), like the
  suggestions: the request never calls Shopee. A short link (s.shopee.vn) is only asked where it redirects, to
  read the item id from the address; the product page is never opened. `productOfferV2` then gives the rest.
- **The link a member pasted stays the product's link**: their own affiliate link, used on a Page without a Shopee
  account. A product page's link (shopee.vn/...) is kept as the page instead.
- **Any member's Shopee account may read it**, the member's own first, like the daily check: what Shopee says
  about a product is not private (2026-11-03). Without one in the team, pasting is refused and points to the file.
- **Shopee Affiliate's "Lấy link hàng loạt" CSV** is imported without Shopee (item id, name, price, shop,
  commission, product page, affiliate link). It has no stars, sales or shop type, so those start at 0 / "Shop
  thường" and the worker fills them when the team has an App ID; otherwise a member does before approving.
  Its "Doanh thu" column is not used: it is not clear whether it counts sales or money, and a wrong sales
  number would let a product pass the 100-sales rule. A product already listed (same item id) takes the file's
  link and figures and keeps its approval unless it no longer meets the rules.
- Typing every field stays, behind "Nhập tay", for TikTok Shop and for fixing a row by hand.

## 2026-11-04 — The interface keeps orange for the main action and where you are; statuses are a dot and a word

Asked by the owner ("giao diện hơi AI, cho tự nhiên hơn"). Orange had spread to every info banner, "processing" tag
and the solid selected menu item, so it no longer pointed at anything. Now: primary buttons stay the icon's orange;
the selected menu item is a light grey fill with deep-orange text; information is a quiet slate blue. Statuses
across the app are `StatusText` (a dot and a word) instead of tinted tags; details are joined with commas or set on
their own lines instead of "·"; no all-caps labels or decorative shadows; empty thumbnails are grey. The 30-day plan
(its tab, the "Tạo video" dialog, its banner) follows the same rules. Only text the api writes (the LLM label
"DeepSeek · deepseek-chat") keeps its "·". The video template and its render are not touched.

## 2026-11-04 — The 30-day plan gets a Backlog, posting times and 48-hour numbers; no stored winner flag

Asked by the owner on /knowledge and in docs/specs/plan-tab-improvements/brief.md. Adds to the 2026-11-03 plan
decision without reversing it:

- **A Backlog of ideas with no day** (`topic_plan_items.day` null), as its own tab. Ideas move between it and the
  days by dragging or "Xếp vào ngày…"; the 5-a-day limit does not apply there (300 at most) and a topic is still
  never twice in the group. **Saving an imported or AI plan replaces the 30 days only**: the Backlog stays, but for
  an idea the new plan puts on a day. A file without days can only be added to the Backlog.
- **Videos can be made ahead.** "Tạo video" lists the coming days' and the Backlog's ideas, not only today's. Each
  group has 1–5 posting times; the n-th idea of a day is suggested to go out at the n-th, and "Đăng" for its video
  starts on "Hẹn giờ" at that time. The time typed there is Vietnam time whatever the browser's time zone (before,
  it was the browser's). Moving an idea does not move a post already scheduled; the member is told so.
- **Two statuses more**, read from the video's posts, never stored: "Đã lên lịch" and "Đã đăng".
- **No stored winner flag**, keeping the 2026-11-03 decision: a card shows each Facebook post's 48-hour numbers
  against its Page's median and the share/view goal, and is drawn bold from 10× only when shown. Only the `48h`
  reading is used, never `latest` in its place, so posts are compared at the same age.
- **"Tiến độ verdict" only counts** the group's videos against `video_target`; the verdict is still decided by the
  team in a meeting once enough videos are posted and measured at 48 hours. The garden group's target is set by
  hand on the page, never seeded by its name in code.

## 2026-11-04 — A reel's numbers survive a Video Insights metric Meta retires

Every post on "Bài đăng" showed "Lần đo gần nhất lỗi: Facebook không còn reel này hoặc chưa có chỉ số". The app
asks all of a reel's metrics in one call, and Meta answers (#100) for the whole call once it has retired one of them,
as it did `post_impressions_unique` in June 2026. Now a (#100) is followed by one call per metric, as Page Insights
already does. A retired metric is null (the reach, "tiếp cận", for now) and logged, and the rest are kept. That
costs about ten more calls per reading. They are cheap (one reading a day per followed post), and cheaper than
guessing Meta's replacement name: a metric is swapped only once Meta's documentation confirms its name.

## 2026-11-04 — Pages fill a wide screen; "Video đã đăng" on Affiliate gets filters

On the owner's call: the content column stopped at 1464 px, leaving an empty band on a large screen, so it now
has no maximum width. Grey explanation paragraphs keep their own ~820 px limit, for reading. The "Video đã đăng"
tab of Affiliate, the one that opens first, had no filter while the list grows with every post; it gets tabs by
product state, a title search and a platform filter, all in the browser like "Bài đăng", with no api change.
## 2026-11-04 — "Bài đăng" filters by status tabs, lists failed posts and holds the calendar as a view

Taken from a look at another posting tool's history screen, on the owner's call. Replaces the status Select and the
"Đang ẩn N bài đã hủy/xóa · Xem" line of the 2026-11-03 entry ("Bài đăng" hides cancelled and deleted posts by
default), and the separate "Lịch đăng bài" menu item.

- The status filter is a row of tabs with counts: "Đang hoạt động" (still the default), "Đã đăng", "Đã hẹn lịch",
  "Thất bại", "Đã hủy/xóa" and "Tất cả". The counts follow the search and Fanpage filters, so a tab says what it shows.
- A post on its way to Facebook ("Đang đăng") and one whose publish job failed ("Thất bại", with the reason and
  "Thử lại") are now listed; before, a failed post showed only on its video's page and in Job logs. "Thất bại" is
  read from the video's last publish job, not stored: the post stays `pending`, the row that job and its retry work on,
  so there is no migration and no second place to keep in step.
- "Danh sách" and "Lịch" switch on the same page (`/posts?view=calendar`); `/calendar` redirects there.
- Every post row has the same icon buttons in the same places ("Xem Reel", "Thử lại", "Kiểm tra", "Hủy đăng"/"Xóa"),
  greyed out with the reason in their tooltip when they do not apply, so the rows line up.

## 2026-11-03 — Clips from a pasted link, TikTok included; picture tools under the picture

Owner's request: taking a photo from Google by its link worked well, and should work for videos and TikTok too.
Google and TikTok are still not stock sources in "Chọn từ kho ảnh/video" (the owner dropped that idea; the
2026-11-02 reasons stand: no usable API, scraping breaks their terms). Instead:

- **One link endpoint for photos and clips.** `POST /scenes/{id}/media-from-url` replaces `image-from-url`
  (`remote_images.py` is now [remote_media.py](../api/src/reels_api/remote_media.py)) and takes a photo's link, a
  video file's link (MP4, MOV, WebM) or a TikTok video's link; what was downloaded decides whether it is a photo or
  a clip. Same public-internet-only rules; the download may be a clip's 50 MB and take up to 60 s, still inside the
  request (like the photo link, not a job: the member waits for it on the scene).
- **TikTok through yt-dlp.** A link on `tiktok.com` (any subdomain, short `vt.`/`vm.` links included) is handed to
  [yt-dlp](https://github.com/yt-dlp/yt-dlp), which reads the page and fetches the video from TikTok, the largest
  size offered, H.264 before HEVC. Photo posts, profiles and other lists are refused. The owner accepts the risk of
  reusing other people's TikTok videos (copyright, "unoriginal content" on Facebook and YouTube): the member who
  pastes the link chooses the video and is responsible for it, as for an upload. A clip's link is not stored (the
  scene has no column for a clip's source).
- **A linked clip over 60 s keeps its first minute** (cut without re-encoding), since TikTok videos often run longer
  than a scene's clip may be; an uploaded file still has to be 60 s at most.
- **"Tìm trên TikTok"** beside "Tìm trên Google" opens TikTok's video search on the scene's first keyword, to copy a
  video's link and paste it back; Google Ảnh still opens on tall photos.
- **Picture tools in the picture's middle.** On hover, "Xem" (new: the scene large in its 9:16 frame, photo or
  clip, with its text switchable on and off), "Chỉnh khung"/"Cắt video", "Vị trí chữ" and "Xoá video" are stacked in the middle of the scene's picture
  instead of along its bottom edge; "Thay" is gone ("Tải lên" does the same). The crop, trim, text
  position, paste and stock dialogs open in the middle of the screen; crop and trim put the picture on the left and
  their controls beside it, so "Áp dụng" is reached without scrolling.

## 2026-11-03 — Pexels is the default stock library; team defaults are edited, then saved

Owner's request. Pexels comes first everywhere a stock photo is looked for: the picker opens on it,
"Tìm ảnh" searches it (the api's default `source`), and "Tự tìm ảnh" asks Pexels, then Pixabay, then
Openverse. Without a Pexels key the first source offered is used. This replaces the Pixabay default of
"“Tìm ảnh khác” can search any stock source", "The picker offers three stock sources" and the order in
"“Tự tìm ảnh”: jobs now pick stock photos after the script" (below).

"Thiết lập mặc định" is no longer saved at each change: it is read-only until "Chỉnh sửa", and "Lưu"
sends every change together ("Huỷ" drops them), so a half-done change never reaches new videos. A
video's own "Thiết lập" tab still saves at once.

## 2026-11-03 — "Bài đăng" no longer suggests posting a video to another Page

Owner's call: the "Đăng thêm lên Page khác" card is gone. It suggested sending the same MP4 to a second Page, which
docs/specs/multi-platform/plan.md warns against: Meta shows a copy less and can stop paying a Page that repeats
content. In its place, from the same "did well" reading (a post reached its Page's usual 48-hour views, or the
Page has too few measured posts), two cards beside "Sẵn sàng đăng": "Nên làm bản TikTok" (no TikTok version yet,
opens "Tạo bản TikTok") and "Nhân bản cho Page khác" (no Facebook clone yet and missing from a working Page, opens
"Nhân bản" with a request for a real variant). Both make the member's choice one click; each costs one LLM call
only when the member confirms.

## 2026-11-03 — Forms open in a drawer, not a centred dialog

Owner's request ("chuyển tất cả các modal sang drawer"), narrowed with the owner to the dialogs holding a form: a
drawer keeps the page in view beside the form and scrolls a long form inside it (the product form no longer runs
off the screen). Dialogs that need the whole screen (photo and clip editors, stock picker, previews, numbers) and
yes/no confirmations stay centred dialogs. One component, `FormDrawer`, takes the props the form dialogs took, so
the screens read alike; see [ux-guidelines.md](ux-guidelines.md).

## 2026-11-03 — Affiliate accounts, links and revenue belong to one member

Owner's call on issue #47 ("tài khoản aff dùng mỗi người một tài khoản riêng"; "thành viên có được xem hoặc sửa tài
khoản aff và doanh thu của người khác không? Không"). This is the first data in the app that belongs to one member,
next to "There is no self-signup and there are no roles: every member can manage users" (2026-10-31), which stays
true for everything else.

- **Accounts** (`affiliate_accounts`, migration 0031): each member adds their own Shopee accounts (with the Open
  API's App ID and Secret) and TikTok accounts on Cấu hình › Tài khoản affiliate. Every query is narrowed to the
  signed-in member; someone else's account answers as if it did not exist.
- **Shopee's App ID and Secret** are a new kind of key stored encrypted in the database, like a Fanpage token: they
  only go in, and only the last characters of the Secret are shown.
- **Pages have an owner** (`fanpages.owner_id`): the member who connected it, the one who last touched it for Pages
  already there. Only the owner sets its Shopee account (one of their own); a Page that belongs to nobody is
  taken by a member for themself ("Nhận Page này"). There is no handing a Page to another member: the owner found it
  unneeded, and a Page with an owner keeps it.
- **Orders** read from Shopee are shown only to the account's owner ("Doanh thu" on `/affiliate`).
- The product list stays the team's: what Shopee says about a product is not private.

## 2026-11-03 — Products per platform; Shopee suggestions and links through its API, never by scraping

Owner's request on issue #47 ("tôi không thể tự tìm thủ công được"). Replaces "Affiliate products are approved by
fixed rules" (2026-10-31) only in that the rules now depend on the platform.

- **Two platforms.** A product is Shopee's or TikTok Shop's (`affiliate_products.platform`). Shopee keeps its rules
  (Mall / Yêu Thích+ / Yêu Thích, 4.7 stars, 100 sales, no banned word) and adds "the commission has not expired".
  TikTok Shop's are the proposal in the issue, still waiting for the owner: TikTok Shop Mall or a shop scoring at
  least 4.0, 4.7 stars, 100 sales, a commission above 0, no banned word. They live in `affiliate.py` alone.
- **Shopee's Affiliate Open API, not scraping.** Scraping Shopee breaks its terms, is blocked by its bot checks, and
  gives no affiliate link anyway. The worker searches `productOfferV2` with the script's product ideas, using the
  asking member's own account, keeps up to 5 products per idea that meet the rules, best first (money per sale,
  weighed by stars and sales), and a member presses "Chọn". Without an account, each idea opens Shopee Affiliate's
  own search.
- **Each Page gets its own link.** When the worker writes a reel's comment on a Page whose owner set a Shopee account,
  it makes that account's short link once per product, video and Page (`generateShortLink`, sub ids `v<video>` and
  `p<page>`, kept in `affiliate_links`), so an order names the video and Page. A Page without one keeps the link a
  member pasted. A Shopee failure is recorded on the post like a Facebook one and waits for a member.
- **Not jobs.** Suggestions, the daily check of approved API products (back to draft when Shopee no longer offers one
  or it fails the rules) and the daily reading of orders are worker rounds between jobs, like the post numbers: a
  request never calls Shopee (except "Kiểm tra kết nối", one search, like the AI providers' check), and nothing
  loops. A suggestion job would also have fought the photo search for the video's one active job.
- Shopee publishes its API documentation only inside the affiliate dashboard. The signature, field names, sort and
  shop type codes follow third-party clients and are tested only against the fake service; `shopee.py` is the one
  place to change them, and a member with an App ID should try it once for real.

## 2026-11-03 — A TikTok version is its own video, cloned from the Facebook one, and posted by hand

Owner's choice on issue #47, following docs/specs/multi-platform/plan.md: one file must not go to two platforms,
and TikTok's money comes from TikTok Shop's cart, set only in TikTok's app.

- **A video has one platform** (`videos.platform`, Facebook for every video before). "Tạo bản TikTok" is "Nhân bản"
  with a request filled in (a question as the hook, a short caption, few hashtags, 1–2 other scenes and photos) that
  the member may change; the new video names its source (`variant_of_id`) and both pages link to each other. It
  costs one LLM call, like any clone.
- **Products follow the video's platform**: a Facebook video takes Shopee products (links in the comment), a TikTok
  version TikTok Shop products (the cart).
- **Posted by hand.** The TikTok version's "Xuất bản" has the MP4, the caption, the cart's products and a checklist
  (AIGC label, cart, disclaimer, TikTok's own music); "Đã đăng tay" records the post with its link on one of the
  member's own TikTok accounts (`publications` with `platform = tiktok`, no `remote_id`, so no Facebook reading
  touches it). Posting through TikTok's API, and reading its numbers, stay with issue #46.

## 2026-11-03 — Pages showing Facebook data ask for a fresh reading when opened

Requested by a member (namtc): "Kết nối Fanpage", "Bài đăng" and "Bình luận" should not wait for "Kiểm tra ngay",
"Cập nhật view" or "Tải bình luận mới" to be pressed. Opening one of them calls its `POST .../freshen`, which asks the
worker for what has not been read in the last 15 minutes: the Pages in use, the posts still followed (an hour to 14
days live), the reels followed for comments. This keeps the earlier rules: a request still never calls Facebook,
nothing already asked for or read minutes ago is asked again (so five members opening the page add nothing), and posts
older than 14 days are still read only on "Cập nhật view". The buttons stay for asking at once.

## 2026-11-03 — "Tự viết": a video without the AI, which then has no AI safety review

Owner's request ("tạo video mà không cần theo prompt"). "Tạo video" can make a video with no LLM call: the member pastes a
script or writes it on the video page. Choices, as proposed to the owner and taken while the owner had not answered them
yet (open to change):

- **Paste and blank in one** ("A + B"): the script field is optional. Each paragraph is a scene, and "Đọc:" lines are its
  voice text, a plain-text format with no AI and no hidden parsing. An empty field gives one empty scene.
- **The topic group is still required** (banned words, team defaults, the 30-day plan), but not its script prompt.
- **No AI safety review, said plainly.** A hand-written video has no self-review. The app shows "chưa được AI rà soát an
  toàn" on the video page instead of an empty list, which would read as "nothing to fix". It does not block posting,
  just as banned words only warn (2026-10-31).
- `videos.hand_written` (migration 0030) marks such a video. It is stored, not derived from the jobs, because a video
  with no job and one whose jobs were pruned look alike.

Nothing logged is reversed: the AI path, "Prompt text is app data; the output format is code" and the clone stay as
they were.

## 2026-11-03 — The listener's volume is per browser and never part of the video

Owner's request ("tăng giảm âm lượng ở các chỗ phát video"). The preview had no volume control at all, and the MP4 player
in "Xuất bản" is too narrow for the browser's own slider. One control ("Tắt tiếng" and a 0–100 % slider) now sits in
the preview, under the MP4 and in "Cắt video". It multiplies the video's own mix, so the music, narration and ducking keep
their proportions, and it changes nothing that is rendered or posted. It is kept in `localStorage`, a per-viewer
convenience, the same level for every player. The video's own levels stay on "Thiết lập".

## 2026-11-03 — Post analysis: watch time, reach and a retention curve read against the posted scenes

Owner's request ("thời gian xem trung bình, kiểu các chi tiết phân tích video"). The same Video Insights call (no extra
request) now also asks for `blue_reels_play_count`, `fb_reels_replay_count`, `post_impressions_unique`,
`post_video_avg_time_watched`, `post_video_view_time`, `post_video_followers` and `post_video_retention_graph`. All of them
are documented by Meta for Reels, lifetime only (migration 0029, new columns on `post_metrics`).

- **The curve is read against the scenes that were posted.** The publish job keeps `publications.scene_marks` (where each
  scene starts and ends in the MP4 it uploads), so later edits never move them. "Phân tích bài đăng" names the scene
  that loses the most viewers. Posts from before have no marks and show the curve alone.
- **Shapes not yet seen on a real Page.** The retention graph is documented as percentages by segment, with no segment
  count for Reels. The app keeps fractions in segment order (values above 1.5 are read as percent) and spreads them
  evenly over the reel. As with the first numbers (2026-11-03, post numbers), a member checks them against Meta Business
  Suite, and `facebook.reel_insights` is the one place to fix.
- **Not taken:** audience age, gender, country and traffic source. Meta lists them only for regular videos, so whether
  Reels give them must be tried on a real Page first.
## 2026-11-03 — CI runs in parallel; draft PRs skip E2E, docs-only PRs skip CI

A full run took about 16 minutes: E2E alone was 13 (one test after another, each render-heavy one
30–60 s) and api pytest 10. E2E and api pytest now each run on four machines, each machine taking
every 4th test (Playwright's own `--shard` splits in file order and would put all of
`videos.spec.ts` on two of them). Running pytest in 4 processes on one machine (`-n 4`) was tried
first and saved almost nothing: the runners of a private repo have 2 vCPUs; it stays for local runs. A draft PR runs lint, typecheck, pytest and
the Cloudflare build only, so members who push often without testing locally get feedback in a few
minutes; E2E and the Docker image job run when the PR is marked ready for review. A PR that changes
only `docs/` or `.md` files runs no CI. A push to `main` still runs every job before it deploys, so
the 2026-10-31 rule that only CI deploys, after every test passes, is unchanged. Cost: more runner
minutes per run, since each machine sets itself up.

## 2026-11-03 — "Video thắng" is dropped from the app

Owner's call, replacing the "Video thắng" part of the earlier 2026-11-03 entry ("Video thắng" is 10× the median of its
own Page over 60 days). At 1–3 posts a day a 10× outlier is rare, so the tag, the "Chỉ video thắng" filter and the KPI
card were almost always empty and gave no signal. Gone: the `is_winner` flag, the weekly `winners` count and the
`winner_factor` rule in the api, and everything showing them. Kept: each Page's 60-day median at 48 hours, a post's
multiple of it ("Gấp N× trung vị Page", from 5 measured posts), the share/view goal and the weekly KPIs. The team's
winner rule and the planned "Winner variants" go from docs/content.md and docs/project.md too, on the same call; issue
#44 (variants of a winner) needs a new trigger if it is picked up.

## 2026-11-03 — "Bài đăng" hides cancelled and deleted posts by default

Cancelled and deleted posts still stay on "Bài đăng" (2026-11-02): they are the only record of who took a post down
and when, or that Facebook did, with the views read before. But day to day the team looks at live and scheduled posts,
so the status filter now starts at "Đang hoạt động" (scheduled and published) and a line under the table counts what it
hides, with "Xem" to show everything. Only the default view changes; no post is removed.

## 2026-11-03 — "Bài đăng" is one table grouped by video, with no grid

Replaces the "one card per post, grid or list" part of the earlier 2026-11-03 entry ("Bài đăng" looks like "Video"),
on the owner's call. With a card per post, "Bài đăng" and "Video" looked the same, a video posted three times showed
its title three times, and the list needed nine columns and a sideways scroll. Now each video is one row (thumbnail,
title, how many posts on which Pages, their statuses, total views, latest time) that opens to its posts, each with its
own Page, time, status, views and actions. The grid is dropped here only: posts are read as numbers, while "Video"
keeps grid and list for working on videos. The api is unchanged; the grouping and filters still run in the browser.

## 2026-11-03 — The post metrics migration is 0024, not 0023

The topic plan (#79) and post metrics (#84) branches each added a migration `0023` after `0022`, and both
were merged, so `alembic upgrade head` failed with two heads. Production got only the topic plan's `0023`
(#79 deployed; nothing after it could pass CI), so the post metrics migration is renumbered to `0024`, after
`0023_topic_plans`. This is the one exception to "never edit a migration on `main`": the file was never applied
outside development, and two files with the same revision id cannot be fixed by adding a third. The post
metrics entry below says "migration 0023"; read 0024. `api/tests/test_migrations.py` now fails CI when two
migrations share a number or the history forks. A development database that ran the old post metrics `0023`
must be reset (drop and recreate it, then migrate).

## 2026-11-03 — Scene voice texts tell the food's benefit, with an optional short eating tip

Issue #70: narration sounded like a cooking lesson, because the fixed output format asked for "lý do, cách ăn hoặc
mẹo nhỏ" and all five voice texts in its worked example described cooking (fried, boiled, roasted…), which the model
copies closely. The format's voice rule now asks for the benefit (what the food contains, which part of the body it is
good for, who it suits), one short eating tip only when there is room (when, how much), no cooking steps, the soft
wording "tốt cho" / "hỗ trợ", no promise to cure, and no word-for-word repeat of the on-screen text. The example's five
voice texts are rewritten that way and still open with the dish (2026-11-02 holds: the rule itself still does not
require the dish name, since not every topic has dishes). It is code, not app data, so it applies to "Tạo kịch bản" and
"Nhân bản" alike; existing videos keep their voice texts until their script is written again.
## 2026-11-03 — "Kết nối Fanpage" is a card per Page; only a Page never posted to can be deleted

Requested by a member (namtc07): some Pages are no longer used and cluttered the table. The screen now shows one card
per Page in use, broken ones first, and folds stopped Pages away. "Xóa" removes a Page with its token and numbers, but
only once it is stopped (so a slip cannot remove a Page in use) and only if it never had a post: "Bài đăng", the
per-Page medians and who posted what point to its row, as users are disabled, never deleted (2026-10-31). A Page with
posts stays stopped and folded away.

## 2026-11-03 — "Bình luận" answers visitors as the Page; Page Insights are read at each check

Requested by a member (namtc07) on issue #71, with the Page token's `pages_read_user_content`,
`pages_manage_engagement` and `read_insights`.

- **"Bình luận"** is a page under "Đăng bài" with the visitors' comments under the reels the app posted in the last 14
  days, read by the worker every 30 minutes between jobs (not a job, as with the post numbers). Members answer as the
  Page, hide spam, or set a comment aside. Replies are written by members only: no AI reply, since every Claude call
  costs money and a wrong answer goes out under the Page's name; a suggestion a member approves can come later.
  Comments on posts made outside the app are not read. Commenters' names and words are stored, as they are public on
  the Page.
- **Never sent twice**, by the same rule as reels and the affiliate comment: stamped before Facebook is asked, a
  failure waits for a member, and a retried reply first looks for the Page's reply with the same text.
- **Page Insights** (views, reach, engagements per day) are read with each token check, the last 7 days rewritten
  since Facebook revises them, one metric per call so a retired one loses only its number. Meta retired
  `page_impressions` on 15 November 2025; the names used (`page_media_view`, `page_total_media_view_unique`,
  `page_post_engagements`) are from Meta's deprecation notes, tested only against the fake service, and
  `facebook.PAGE_METRICS` is the one place to change. A day is Facebook's (Pacific time), not Vietnam's. A token
  without `read_insights` is not a broken connection: the numbers say why they are missing.
- **Not built from the same list:** photo and text posts (`pages_manage_posts`) wait, for the "unoriginal content"
  risk above; editing the Page's details (`pages_manage_metadata`) is a one-off per Page; finding new Pages in Business
  Manager (`business_management`) would mean keeping a user token, which the app does not (2026-10-31).

## 2026-11-03 — The app writes the affiliate comment under a posted reel; products are chosen before posting

Requested by a member (namtc07) on issue #71, with the Page token's `pages_manage_engagement`: the pinned comment and
its Shopee links were copied and pasted by hand under every reel.

- **What.** Once a reel is live, the worker writes the video's pinned comment followed by "name: link" for each
  attached product that is approved and still meets the rules, as the Page. Pinning stays manual: Graph API cannot pin.
- **Who decides.** "Đăng" has "Tự bình luận", on by default; posts made before this have it off and get a comment
  only when a member presses "Bình luận ngay".
- **Never two comments.** Like a reel (2026-10-31), the attempt is recorded before Facebook is asked, Facebook's
  comment id is kept and a later change edits that comment. An attempt whose answer was lost is not retried by itself;
  a member's retry first looks for the Page's comment with the same text (`pages_read_user_content`).
- **Not a job**, as with the post numbers: the worker writes up to 3 due comments between jobs, 2 minutes after a
  reel goes live; a request never calls Facebook, and a failed comment waits for a member, never looping.
- **Products before posting.** This replaces "products attached to each posted reel": a video takes products at any
  time, on its own page, so the first comment already holds their links. Changing them later edits the comments
  already written. `/affiliate` still lists only posted videos.
- Meta's docs name `/{object-id}/comments` for Page posts; that a reel's video id takes comments the same way is
  tested only against the fake service, so a member should look at the first comment on a real Page.

## 2026-11-03 — The worker checks each Page's token twice a day and keeps its followers

Part of issue #71, agreed by a member (namtc07). The issue's weekly "Bộ nhiệm vụ" (a playbook of Facebook's Page
tasks, counted and done by the app) is not built: Graph API does not give Facebook's task list, a tracker alone would
copy the Professional Dashboard with a different percentage, and posting photo or text posts by itself risks
"unoriginal content" with stock photos. What the team needs first, with more Pages, is to know when one breaks.

- **What is checked.** The worker reads `GET /{page-id}?fields=name,followers_count` with the Page's token, 12 hours
  after the last check, at once for a Page just connected or given a new token, and on "Kiểm tra ngay". A token that
  no longer works (its maker changed their password or lost the Page) shows on "Kết nối Fanpage" with what to do, and
  "Đăng" warns before posting to it. Only a dead or refused token is found this way: which permissions a Page token
  has needs a user or app token the app does not keep, so a missing `read_insights` still shows on the post.
- **Not a job**, for the reasons the post numbers are not one (below): the worker checks up to 3 due Pages between
  jobs, a request never calls Facebook, and a failed check waits for the next one instead of looping.
- **Followers** are kept once per day (Vietnam time) in `fanpage_followers` (migration 0025), so "Người theo dõi" shows
  the gain since the last number before this week's Monday. The week runs Monday to Sunday like the KPIs on "Bài
  đăng", not Sunday to Saturday like Facebook's weekly tasks: one kind of week in the app.
- **The Page's name** follows Facebook: a Page renamed there is renamed in the app at its next check.
- **No new menu yet.** The status lives on "Kết nối Fanpage"; a "Quản lý Page" menu waits until there is more than
  this to show.

## 2026-11-03 — "Bài đăng" looks like "Video": thumbnails, grid or list, search by title

Part 2 of issue #74. `/posts` shows one card per post with its video's title-scene thumbnail, so a
member recognises the video at a glance, and switches between grid and list like `/videos`; the
choice is remembered per page, in the browser only. The search by title and the filters run in the
browser over the list the api already returns whole, because the team has at most a few hundred
posts; the api gains only `thumbnail_url`. A video with several posts has several cards, one per
post, since each post has its own Page, time and actions.
## 2026-11-03 — Each topic group has a 30-day plan of video ideas; "Tạo video" follows it

Owner's plan "Kế hoạch chủ đề 30 ngày" (tasks 1.1–3.7; task 4, the content research and trial week, happens outside
the code). Each group on `/knowledge` holds 30 days of 3–5 ideas (topic, pain group, viewer's pain, hook angle),
imported from JSON/CSV, written by AI or typed in. Choices made while building it:

- **Status is read from the video, not stored** (Ý tưởng, Đã tạo video, Đã viết kịch bản, Xong = has an MP4), and
  deleting a video unlinks its idea through the foreign key, so the status can never disagree with the video.
- **3–5 a day:** more than 5 is refused everywhere; fewer than 3 only warns, so a day can be filled one idea at a
  time.
- **"Tạo bằng AI" is a job** on the queue like scripts (`jobs.kind = plan`, belonging to a topic group, so
  `jobs.video_id` is now nullable). It writes 10 days per LLM call, three calls, because one answer for 120 ideas
  passes the output limit; each call gets the topics already chosen. The result waits as a draft and replaces the
  plan only when a member saves it, as an imported file does after its preview. The plan prompt is app data, its
  JSON format is code, as for scripts.
- **Saving a new plan replaces every idea** but keeps the video of an idea whose topic is unchanged, so the plan
  can be adjusted after the first week (task 4.5) without losing what was made.
- **Pain and hook reach the script** through `[Nhóm nỗi đau]`, `[Nỗi đau]`, `[Góc hook]` in the script prompt, or
  appended. The default script prompt is unchanged; the pain-first prompt (task 4.3) is the team's to write.
- **A topic outside the plan only gets a note**; videos are still made without a plan, as before.
- "Hôm nay" is the Vietnam date counted from the group's start date.

## 2026-11-03 — "Video thắng" is 10× the median of its own Page over 60 days; KPI weeks run Monday to Sunday

Part 3b of issue #74, agreed by a member (namtc07) on the proposals in the issue. The team's rules (docs/content.md) stay
as they are: a winner is at least 10× the median views, the share/view goal is 0.2 %. What they are measured against:

- **The 48-hour numbers only**, so every post is compared at the same age.
- **Per Page, over the last 60 days.** The performance-loop brief took every post ever made; against a growing Page's
  first weeks, or a large Page's numbers, almost every video of a small or newer Page would win, or none would.
- **At least 5 measured posts on the Page** before any of its posts is flagged, as the brief said; under that the page
  says "Chưa đủ dữ liệu để so trung vị".
- **A KPI week is Monday to Sunday in Vietnam time**, this week shown against last, counting the posts that went live in
  it and have their 48-hour numbers. The share/view figure counts posts with both numbers.
- **Nothing is stored**: the median, the flag and the KPIs are worked out from `post_metrics` on each request, which
  is cheap at 1–3 posts a day.

The brief's "Đề xuất biến thể" (Claude proposes 10 variants of a winner) is not part of this and stays open in #44.

## 2026-11-03 — Post numbers: the worker reads them between jobs, daily for 14 days, and keeps the 48-hour mark

Part 3 of issue #74, agreed by a member (namtc07) on the issue's open questions. "Metrics and analytics in the MVP" is
taken out of Out of Scope in `docs/project.md`: the team's KPIs and its winner rule (`docs/content.md`) need the numbers,
and "Nhân bản" has no way to know which video won without them.

- **Per post, not per video.** Since a video can have several posts (2026-11-02), numbers belong to a `publications`
  row (table `post_metrics`, migration 0023).
- **Two readings kept.** `latest`, rewritten by every reading, which "Bài đăng" sorts by; and `48h`, the first reading
  at least 48 hours after the post went live, never rewritten, so the median and the winner flag (next PR) compare
  posts at the same age. A post more than a day past its 48-hour mark when first read (older posts at deploy) gets no
  mark rather than a wrong one. This replaces the performance-loop brief's "only 48h, a manual re-reading overwrites
  it": a member wants the current views too, and overwriting the mark would break the comparison.
- **Not a job.** The brief's `metrics` job would lock the video (one active job per video) for every reading and fill
  the Jobs list; a reading only writes numbers, so the worker reads due posts itself between jobs, at most 3 every 5
  seconds with a 10-second timeout per call. A request never calls Facebook: "Cập nhật view" only asks the worker. A
  failed reading is recorded on the post and waits a day (or another "Cập nhật view"), never looping.
- **When.** An hour after a post went live, then daily for 14 days; after that only on "Cập nhật view". Video Insights
  is free to read, and at 1–3 posts a day this stays far under Facebook's limits.
- **Which numbers.** Views are Video Insights' lifetime `fb_reels_total_plays` (every play, replays included); shares and
  comments from `post_video_social_actions`; reactions are `post_video_likes_by_reaction_type` summed. These names are
  from Meta's docs and tested only against the fake service; a member must check them against Meta Business Suite on a
  real Page, and `facebook.reel_insights` is the one place to change. The Page token needs `read_insights`; without it
  the post says so in Vietnamese and the member pastes a new token.

## 2026-11-03 — A reel posted by the app gets the title scene as its cover

Requested by a member (tuananh219ln): Facebook picked a frame from the middle of a reel ("1. Canh bí đao…") as its
cover instead of the title. After the reel is live or scheduled, the publish job sends the first frame of the MP4 the
reel holds, which is the title scene with no fade-in, as its preferred cover (Video Thumbnails edge, which Meta's Reels
guide links for a custom cover). It is taken from that MP4, not from the app's thumbnail, so the cover matches the
posted video even if the title changed after the render. A cover is cosmetic, so one Facebook refuses never fails the
post or makes it retry; Facebook then keeps its own pick and the worker logs why. Meta's docs do not say the edge
works on reels, so this is tested only against the fake service, and a member should check the cover on the Page
after the first post. Reels posted before this keep the cover they have.

## 2026-11-03 — ChatGPT controls drafts through private MCP and member-authorized OAuth

Requested by the owner. The private connection searches/reads videos and topic-group names, edits
scene text/voice text and posting text, creates a video with a script job, and queues a render.
It calls the same editor handlers, so validation, locks, pre-render checks and job attribution
stay in one place. It has no publishing, deletion, credential or user-management tools. Creating
scripts and narration uses the team's existing paid services; no OpenAI API key is needed for the
MCP layer itself.

The implementation uses the official MCP Python SDK with stateless Streamable HTTP behind the
existing web origin. An opt-in `MCP_PUBLIC_URL` enables it; unset keeps it disabled. OAuth is for
delegating an existing member session to ChatGPT, not a new way to sign in or create accounts.
ChatGPT registers a public OAuth client, uses S256 PKCE, and receives opaque rotating tokens
stored hashed in Postgres (migration 0021). Consent is shown in the existing app theme at
`/chatgpt`, and members revoke their own connections there. Connections last at most 30 days;
revoking the originating session or disabling the member also invalidates them. See [chatgpt.md](chatgpt.md).

## 2026-11-02 — The app checks a scheduled post on Facebook after its time, and on "Kiểm tra"

Requested by a member (tuananh219ln): a scheduled reel cancelled on Facebook still showed as "Đã đăng" once its
time passed, because the app counts a scheduled post as published by the clock and never asked Facebook again. The
worker now queues one `check` job per scheduled post, 10 minutes after its time, and a member can queue one with
"Kiểm tra" on any post on Facebook. The check only reads the reel and records what Facebook says; it never posts or
deletes. This is a timer for reading, not for posting: "Scheduling uses Facebook's own scheduling; the app has no
posting timer" (2026-10-31) still holds. A reel found gone after its time ends as "Đã xóa", not "Đã hủy", keeping
the rule that "Đã hủy" never stands for a reel people may have seen; who closed it is left empty ("Trên Facebook").
The automatic check runs once per scheduled time, even if it fails, so a broken token never loops; "Thử lại" and
"Kiểm tra" remain.

## 2026-11-03 — A clip's speed is set per scene; the scene keeps its seconds

Requested by a member (tuananh219ln). "Cắt video" has "Tốc độ clip", 0,5× to 2×, stored as `scenes.video_speed`
(migration 0022; older scenes are 1×, and their MP4s stay current). "Số giây" remains the scene's length on screen, so
the scene takes (seconds + crossfades) × speed of the clip: the crossfades play at the clip's speed too. A part longer
than the clip only warns and holds the last frame, as a short clip already did; the render never fails on it, and the
limit on "Bắt đầu từ giây" stays "1 s of clip left", so changing the speed never makes a saved start invalid. A new clip
starts at 1×. "Xem trước" plays the clip at its speed; the scene card's own player shows the clip as uploaded.

## 2026-11-02 — A re-rendered video can be posted again; posts can be cancelled and deleted from the app

Requested by a member (tuananh219ln). This replaces "A video is never posted to Facebook twice" for a post a member
asks for on purpose: a video now has one `publications` row per post (migration 0020), so a reposted video keeps its
history. The same MP4 still never goes to a Page that holds it: a Page can take a new render of the video, or the same
MP4 once the earlier post was cancelled or deleted, and another Page can take it at any time. When the chosen Page
keeps an older post of the video, the dialog warns that there will be two. What the old entry protects against stays
exactly as it was: a retry of one post reads the reel's status first and never makes a second post.

Taking a post down replaces "changing or cancelling one is done in Meta Business Suite". Facebook publishes a scheduled
reel by itself, so "Hủy đăng" has to delete the reel there; only setting a status in the app would leave it to go live.
A post Facebook never received is closed in the request, its queued job cancelled. Any other goes through a new
`unpublish` job, since only the worker calls Facebook. A running job is never interrupted: the member waits for it. The
job, not the button, decides the outcome from Facebook's status: "Đã xóa" if the reel was ever public, "Đã hủy" if not,
so a cancelled post can never be one people saw. A failed delete leaves the post as it was. Both keep who and when
(`closed_by_id`, `closed_at`) and stay on "Bài đăng", but leave the calendar and the affiliate list.

Only Facebook is built. TikTok and YouTube show in the dialog as "sắp có": each needs an app review before it can post
publicly and an OAuth flow the app does not have (see [project.md](project.md)), and no TikTok delete API was found, so
"Xóa" may never work there. Whether Facebook's delete behaves the same on a scheduled reel could not be confirmed from
Meta's docs and is only tested against the fake service, so a member should try it once on a test Page.

## 2026-11-02 — Pages poll one request at a time and links do not prefetch

The video page loaded slowly in production: measured from Vietnam, any request through the
OpenNext web worker took about 1–2 s (even `/login`, and `/api/me` answering 401), while the
video payload itself takes about 0.04 s on the api. The 2.5 s polls then overlapped, the menu
prefetched seven pages as server renders, and every hashed JS file was revalidated on each load.
Polling now waits for each answer and pauses in a hidden tab, `Link`s do not prefetch, and
`/_next/static/*` is immutable. Sending `/api/*` straight to the api, without the Next.js worker in
the way, would remove most of the remaining delay, but changes "One origin is kept" in
[deployment.md](deployment.md) and is left to the owner.

## 2026-11-02 — Reading speed is a slider from 0.7× to 1.3×

Owner's choice, replacing the three presets (0.9 / 1.0 / 1.1) in "Reading speed is applied with
FFmpeg, not by ElevenLabs" below: a 10% change was too small to hear. "Tốc độ đọc" is now a slider
from 0.7 to 1.3 in steps of 0.05 (marked Chậm, Vừa, Nhanh), stored as the number in
`videos.options.voice_speed` and the team defaults; it is still applied with FFmpeg `atempo`. Values
saved as presets read as the wider levels (Chậm 0.8, Vừa 1.0, Nhanh 1.2), with no migration. The
narration signature now carries `tempo:<factor>`, so narration made at an old Chậm or Nhanh is made
again on its next render (costing ElevenLabs characters once); narration at 1.0 is untouched. The
browser preview reads at the same factor.

## 2026-11-02 — Narration reads the voice text; the on-screen text only stands in for an empty one

Requested by a member (tuananh219ln): the on-screen text is a short label and the voice text explains it, so reading
both repeated the dish and made the video longer. This replaces "Narration reads the on-screen text, then the voice
text" (below), including its "An empty voice text still means a silent scene", and the way "Scripts may run to 150
words" counts its budget. For each scene:

| Voice text | On-screen text | Read |
| --- | --- | --- |
| yes | yes | the voice text only |
| yes | empty | the voice text |
| empty | yes | the on-screen text, cleaned |
| empty | empty | nothing; the scene's seconds set its length |

Cleaning, in [videos.py](../api/src/reels_api/videos.py): a content scene loses its leading list number ("2." or "2)",
otherwise read as "hai chấm"; "2.5 lít" stays) and each line becomes a sentence, so "Canh rau ngót" / "Mát gan, dễ tiêu"
reads with a pause between them. The split follows the line breaks members and the script already write: guessing
it inside a single line from capital letters would break on names such as "Phú Quốc". The title scene is read whole.
The api sends each scene's `spoken_text`, so the preview reads what the render reads instead of a copy of the rule.

Consequences:

- A scene with on-screen text can no longer be silent on its own: the "Giọng đọc" switch turns off the whole video.
- A scene is not re-read when only its on-screen text changes, as long as it has a voice text.
- Every narrated video reads differently now, so existing MP4s show as outdated and their next render buys the
  narration again. Scenes with text and no voice text, silent until now, are read, and a render with narration on needs
  an ElevenLabs key even when no scene has a voice text.
- The 150-word budget now counts the title scene's voice text and the scenes' voice texts only. At 8–15 words (kept
  as they are) a script reaches at most 117 words, about 40 seconds of speech, so the cap no longer binds.
- The output format's worked example now opens every voice text with the dish, because only the voice text is read
  and the model copies the example. The format's rules do not require it, since not every topic has dishes: a topic's
  prompt on `/knowledge` can still ask for something else.

## 2026-11-02 — One app theme in the icon's orange, Be Vietnam Pro

Owner's choice, the first step of a UI refactor that keeps Ant Design: `theme.ts` is the single
source of colours, and the brand colour is the orange of the app's icon (`icon.svg`), replacing the
teal (`#0F3B4C`) the app started with, the antd blue (`#1677ff`) hard-coded beside it, and the green
"RS" badge, which the icon now replaces as the logo. The orange is a fill with white on it (primary
buttons, the selected menu item), as in the icon; small text and thin marks on white (links, tabs,
switches, focus) use a deeper orange of the same hue (`#C2410C`, about 5:1 on white). The interface
font is Be Vietnam Pro, drawn for Vietnamese, loaded with `next/font` so the app serves it itself
(the build downloads it once; browsers never call Google). The video template's font is a separate
choice and does not change.

## 2026-11-02 — The preview opens in a drawer and can ask ElevenLabs for the real voice

Owner's choice: the browser's free Google voice sounds robotic, so the preview now (1) lists the
browser's Vietnamese voices with Edge's neural ones (HoaiMy, NamMinh) first and suggests Edge when
none is there, (2) lets each member pick a voice, remembered in their browser, and (3) offers
"Tạo giọng thật (ElevenLabs)". This changes the entry "Xem trước plays the video in the browser, with a free voice", where ElevenLabs was never called for
a preview: it is still never called just by opening or playing the preview, only by that button,
after a confirmation, as a `voice` job in the queue. The job makes exactly the MP3s a render would
(same text, voice, speed and signature) and stores them on the scenes, so the next render reuses
them and the credit is spent once per text either way; it only moves the cost earlier, and adds
cost only when the text is changed again before a render. The preview also opens as a drawer from
the right instead of a centred dialog, so the page stays in sight beside it.

## 2026-11-02 — The video page shows who else has it open; edit mode stays without "Lưu"/"Huỷ"

Owner's choice. "Lưu" and "Huỷ" for edit mode were considered and dropped: they would reverse the
decision below that fields save one by one, and photos, AI photos and scene changes are written at
once and cannot be taken back. Instead the page shows the other members who have the video open and
whether they are editing, and warns, without stopping, a member who starts editing while someone
else is. Each open page reports every 10 s and drops out after 30 s of silence (table
`video_presence`, migration 0019), polled like the rest of the app, since the web runs on Cloudflare
Workers with no socket to the api. Showing it on the video list was left for later.

## 2026-11-02 — Local development starts with `scripts/dev.sh`, and uv builds the api venv

Owner's choice. Setting up by hand broke in practice: a venv made with the wrong Python (3.14 instead
of 3.12), and a repo folder moved after `pip install -e`, which leaves the editable installs pointing
at the old path (`No module named 'reels_api'`). On macOS/Linux, `scripts/dev.sh` starts Postgres,
rebuilds `api/.venv` with uv on the Python in `.python-version` whenever it is missing, on another
Python, built for another folder or behind a `pyproject.toml`, runs the migrations, then runs api,
worker and web in one terminal. uv only builds the venv: dependencies stay in `pyproject.toml` with
no lock file, and CI and the Docker images still use pip. `docker-compose.yml` names its project
`reels-studio`, so a moved or renamed folder keeps the same Postgres container and data. The
PowerShell steps in the README stay for Windows.

## 2026-11-02 — "Tự tìm ảnh": jobs now pick stock photos after the script

Reverses "jobs never pick photos" (2026-10-31, repeated in later entries), by the owner's choice:
choosing photos by hand was the slowest step of making a video. The reason behind the old rule still
holds: the photo is stored on the scene, shown in the editor and replaced at will before any render,
and the render uses only stored photos. After a script or clone job, a separate `photos` job (so a
search problem never fails the script) gives every scene without a photo or clip one free stock photo
with the picker's rules (tall, big enough, never one another scene shows; Pixabay, Pexels, Openverse
in that order, skipping sources turned off, without a key or failing). It never makes AI photos, which
cost calls. Stock libraries often show the wrong dish for Vietnamese food, so each pick carries
"Tự chọn, kiểm tra lại" (`scenes.image_auto`, migration 0018) until a member keeps or changes it; the
tag never blocks the render. The team can turn the search off on Cài đặt › Nguồn tư liệu ("Tự tìm ảnh
sau khi viết kịch bản", on by default). The E2E reset turns it off, since most E2E tests start from
scenes without photos; one test turns it on.

## 2026-11-02 — Picker filters, and a blocked Pixabay said as such

Owner's choice of filters for "Chọn từ kho ảnh/video": "Hướng ảnh" (Dọc by default, Vuông, Tất cả),
"Ẩn ảnh đã dùng trong video này" (on by default; "Tìm ảnh" also never takes a photo another scene
shows), the scene's keywords as chips, and photos too small always left out. The size bar is a short
side of 640 px of the file the app downloads, not the 1080 px first talked about: Pixabay's and
Pexels' large files of a tall photo are about 720 px wide, so 1080 would hide every tall photo they
have. Colour, sort order and illustration filters were left out as rarely useful. Pixabay answering
through Cloudflare's bot check (an HTML page, seen when a network is blocked) now says the network is
blocked and to switch network or source, instead of "giới hạn lượt tìm, thử lại sau 1 phút".

## 2026-11-02 — AI photo prompts: English content from the script, one shared style from the app

Owner's choice. The script now writes each scene's `image_prompt` in English and adds
`title_image_prompt`, since the title scene used its first line of text (often a question, which
draws nothing useful) and FLUX.1 schnell follows English far better than Vietnamese. These prompts
describe only what is in the photo; how every photo looks (light, the vertical frame, no text, no
logo) is one shared style the image job appends ("<prompt>. <style>"), so a video's scenes match and
the look changes without a new script. The style is app data, edited on Cài đặt › Nguồn tư liệu
(default in [image_style.py](../api/src/reels_api/image_style.py), empty adds nothing), the same
split as prompt text versus output format. Older scripts keep their Vietnamese prompts. Every card,
the title's included, shows "Prompt ảnh AI" to edit.

## 2026-11-02 — The AI image provider is chosen in the app, Cloudflare first, never switched to Gemini by itself

Replaces the 2026-11-01 entry's "the image job's provider is chosen with `IMAGE_GEN_PROVIDER`". Owner's
choice: the team's default is picked on Cài đặt › Nguồn tư liệu ("Nguồn ảnh AI mặc định"); until it is,
`IMAGE_GEN_PROVIDER` still applies (servers set up before keep working), and without it Cloudflare is
used when it is set up (free, about 57 photos a day), else Gemini. Every "Tạo ảnh AI" button has an
arrow to use the other provider for one press. The provider is stored on the job when it is queued
(`jobs.image_provider`, migration 0017), so a retry uses the same one and the job log shows it. When
Cloudflare's free photos for the day run out the job fails and says to choose Gemini from the arrow:
Gemini costs money, so the app never moves to it without a member choosing it.

## 2026-11-02 — An AI photo for one scene, from its card

Owner's choice: usually only one or two AI photos come out wrong, so each scene card has "Tạo ảnh AI"
("Tạo lại ảnh AI" for an AI photo) beside the batch "Tạo ảnh AI cho cảnh thiếu", which stays. It is
the same `image` job with the new `jobs.scene_id` (migration 0016, no foreign key so a deleted scene
keeps its job log row), so it goes through the queue and locks the video like every job. Unlike the
batch it replaces the scene's photo or clip (the card asks first), and a refused prompt fails the job
with the scene's name while the scene keeps its photo. Retrying a failed one keeps its scene. AI photos
are not made when the script is written: many scenes get stock photos, so that would waste calls.

## 2026-11-02 — Photos from any site: paste, drag or "Tìm trên Google"; no Google API

Owner's request: finding a photo on Google, downloading it and uploading it again was slow. Google Images
is not added as a stock source: its only API (Custom Search JSON) is closed to new customers and shuts
down on 2027-01-01, scraping breaks Google's terms and gets blocked, and paid search APIs cost money.
Most of its photos are also copyrighted, unlike the stock sources (free for commercial use, no
attribution), so the app must not pick them by itself. Instead a member takes one by hand: "Tìm trên
Google" opens Google Ảnh on the scene's keyword, and a copied photo, a photo's link or a photo dragged
from another tab is put on the scene in one step. A link is downloaded by the api
([remote_images.py](../api/src/reels_api/remote_images.py)): http(s) only, every connection (redirects
included) must reach a public internet address, 15 MB and 15 seconds at most, then the upload checks.
The link is kept as the photo's `image_source`, so a copyright claim can be traced back; this extends
the 2026-10-31 "no source info" decision for these photos only. A copied photo (no link in the
clipboard) is stored like an upload. Photos taken this way are the member's responsibility, like uploads.

## 2026-11-02 — A person may copy the production database into their local dev database

`docker/pull-prod-db.sh` runs `pg_dump` inside the Coolify Postgres container over SSH and
restores it over the local `reels`, so bugs can be reproduced on real data. Production is only
read. It is run by a person with SSH access, never by an agent (agents still never connect to
production). The copy cancels production's unfinished jobs so a local worker cannot call real
APIs for them, and the stored API keys and Fanpage tokens stay unreadable locally because their
key file lives in production's storage folder, not in the database.
## 2026-11-02 — Reading speed is applied with FFmpeg, not by ElevenLabs

Replaces the speed part of the 2026-11-01 "Video presets" entry. The default model, `eleven_v3`,
ignores ElevenLabs' `voice_settings.speed` ("Speed is not available for the Eleven v3 model"), so
Chậm / Vừa / Nhanh made the same narration. Owner's choice: keep v3's voice and slow down or speed
up the returned MP3 with FFmpeg `atempo` (0.9 / 1.0 / 1.1, pitch kept), which works with every
model and costs no extra characters; ElevenLabs is no longer sent a speed. A non-normal speed now
joins the narration's signature as `tempo:<speed>`, so slow or fast narration made before this fix
(at normal speed) is made again on its next render; normal narration is untouched.

## 2026-11-02 — "Xem trước" plays the video in the browser, with a free voice

Owner's choice from issue #61: the editor previews the video before a render in the browser, not
as a draft render job, so a preview costs no worker time and no API money. It is built from what
the api already draws (each scene's frame without text and its exact text box, clips, music) and
the render's timing, motion and transitions copied into the page, so it is close to the MP4 but
not the MP4; captions and FFmpeg's audio mix are not reproduced. Narration uses the ElevenLabs MP3
when a render already made one for the current text, and otherwise the browser's own Vietnamese
voice (Web Speech API), which is free; ElevenLabs is never called for a preview. The online
Google/Microsoft voices send the narration text to those services, as typing it into their
translator would. The preview can start from any scene and draws a mock of each app's screen (Reels by default, TikTok, Shorts) with generic icons, not the apps' logos, to show what each covers.

## 2026-11-02 — The video editor opens rendered videos read-only; photos are cropped in the browser

Requested by the owner: a finished or posted video could be changed by a stray click (the "MP4
chưa cập nhật theo bản sửa" tag then appears). The video page now has one view/edit mode for the
whole page: a video with an MP4 or a Facebook post opens in "Xem", a draft in "Chỉnh sửa". The
mode only guards the page in the browser; it is not a permission, and the api accepts changes as
before. Fields keep saving one by one when left, as before, so edit mode has "Xong" but no
"Huỷ": uploads and saved fields cannot be taken back, and saving the whole page at once would let
two members overwrite each other. The post texts ("Nội dung đăng") and "Render" stay available in
view mode.

Photos are cropped, turned and flipped in the browser ("Chỉnh khung") and stored in place of the
scene's photo, so the render core, its 9:16 cover crop and the database are unchanged. A cropped
photo keeps its `image_source`: an AI photo stays labelled as AI (see "AI photos for missing
scenes come from Gemini") and a stock photo keeps its URL, so "Tìm ảnh khác" still moves on from
it. The original is not kept: cropping again starts from the cropped photo. A clip is trimmed by
picking its start and end; its own sound stays out of the render (the toggle in the dialog plays
it in the preview only).

## 2026-11-02 — Ideas, features and bugs live in GitHub Issues, not backlog.md

`backlog.md` is removed; its 17 items became issues #41–#57. New work is opened from the forms
in `.github/ISSUE_TEMPLATE/` (Lỗi, Tính năng, Ý tưởng; blank issues are off), so each one says
what, why and which area. Issues can be assigned, labelled, linked from PRs and closed by them,
which a Markdown list could not do for a team of five. Older entries that link to `backlog.md`
mean the matching issue (the Shopee API one is #47).

## 2026-11-02 — `@claude` in an issue or PR comment answers questions, read-only

A comment mentioning `@claude` from someone with write access runs `claude-ask.yml`: Claude reads
the repo and the docs and answers in a Vietnamese comment, so the whole team sees the answer next
to the issue. It cannot change code (the token is read-only and Edit/Write are denied), because
code changes go through a person's branch and PR. Each run is a paid API call, so it never starts
by itself, the same as `/ai-review`.

## 2026-11-01 — Text boxes can be dragged inside the platforms' safe zone

Owner's decisions, from the text round: a member drags a scene's text box on a "Vị trí chữ" dialog, and the box
stays inside a safe zone (x 60–940, y 220–1440 of the 1080×1920 frame) clear of the platforms' top bar, the
right-hand button column and the bottom caption and music area, so text is never covered once posted. The
place is per scene (new `scenes.text_x`/`text_y`, migration 0015) over a video-wide place for content scenes
(`text_position` in the video's options); the title scene moves only up and down, so the thumbnail stays
centred. This changes the template's fixed places only when a member moves a box: without one, every box
is where it was, and the MP4 signature is unchanged. Captions move with the box and go under it when above
would leave the safe zone. The drag works on the exact box image the renderer overlays (`textbox.png`) over
the frame without text (`frame.jpg`), so what is dragged is what is rendered.

## 2026-11-01 — The title can have a look of its own

Owner's decision: "Kiểu tiêu đề" (Giống cảnh, Hộp vàng) stood apart from the new styles and colours. The text
card now has a "Chỉnh chữ cho" switch, Các cảnh or Tiêu đề, and the title can take a look of its own (team
style or Không hộp, colours, opacity) with the same controls, stored as `title_text_style`, `title_text_color`,
`title_box_color`, `title_accent_color` and `title_box_opacity`. "Tiêu đề giống các cảnh" stays the default.
This extends, and does not reverse, "The title scene can keep the yellow box over outlined scenes": a video
with `title_style` "yellow" still renders the original yellow title box, and is shown with the box unticked;
the page no longer offers the two-way choice itself. A scene preview's address now carries only what that
scene is drawn with, so changing the title's look leaves the scenes' cached previews alone.

## 2026-11-01 — Text boxes are the team's own styles; the four preset boxes leave the page

Owner's decision. The "Kiểu hộp chữ" cards are now Không hộp, the team's own box styles and "+ Thêm kiểu":
a member names a style and picks its box colour, opacity (Đặc, Hơi trong 88%, Trong 70%), text and marked-word
colours; "Không nền" draws a style's letters outlined, as Không hộp, in the box colour. Styles are shared by the whole team, kept as one team setting (`text_box_styles`), and any member
can add, edit or delete them. A video copies a style's colours into its own options (`text_style` "box"), so,
like the team defaults, editing or deleting a style never changes an existing video. The colour rows stay
to adjust one video without changing the style. The presets Vàng, Trắng, Tối and Đỏ are removed from the page
(the owner chose removal over turning them into team styles); the render core keeps them so videos made
with them render as before, and the code default for a new video stays the yellow box (the original
template) until the team defaults pick a team style. "Kiểu tiêu đề: Hộp vàng" is unchanged.

## 2026-11-01 — Text colours are free: any text, keyword and box colour, with a warning when faint

Owner's decision for the text and captions round (colours, style presets, text that can be moved). Replaces,
for colours only, "never free colour or size sliders" in the settings roadmap entry below, and the "too faint
colours are not offered" part of the "text colour and no box presets" entry. The text, the *marked* words and
the box (the outline for Không hộp) each take Theo kiểu, a swatch, or any `#RRGGBB` from a colour picker.
Every colour is drawn as chosen; the page warns instead of refusing when a pair is hard to read (WCAG contrast
under 3 against the box or outline). Sizes stay presets. Marked words on Theo kiểu still move off the
text's colour by themselves. The named colours stored before (white, black, yellow, red) are aliases of their
hex values, so no stored video changes; a faint named colour some api call may have stored is now drawn
instead of falling back. Also decided for the next rounds: text can be dragged per scene (a video-wide
position, overridden by a scene) but only inside the platforms' safe zone, clear of the top bar, the right
button column and the bottom caption area; the title scene moves only up and down so the thumbnail stays
centred.
## 2026-11-01 — Scripts may run to 150 words, about 52 seconds

Requested by a member (tuananh219ln): the voice texts felt short of ideas. This replaces the 120-word budget and
the 48-second target in "Narration reads the on-screen text, then the voice text" below: the budget is 150 words,
a voice text is 8–15 words instead of 6–12, and the pre-render check warns above 55 seconds instead of 48. The cost
is a longer video, which may lose viewers before the end. The 90-second block stays.

## 2026-11-01 — The ElevenLabs key can be pasted in the app too

Cài đặt › Nguồn tư liệu also takes the ElevenLabs key (narration), stored encrypted with the other source keys
("elevenlabs") and winning over `ELEVENLABS_API_KEY` in `.env`, which still works when nothing is pasted. It extends
the stock and AI-image keys entry below. Reason: without it the team could not change the narration
key without server access; a bad or missing key showed only "ELEVENLABS_API_KEY", with nowhere to fix it in the app.
Like every key on that page it is shared by the whole team, not per member.

## 2026-11-01 — The title scene can keep the yellow box over outlined scenes

Requested by a member (tuananh219ln): the title in the yellow box, the scenes in yellow letters with a
black outline. The style and colour were one choice for the whole video, so a third choice, "Kiểu
tiêu đề" (Giống cảnh, Hộp vàng), draws the title on its own. The yellow is the template's `#FFD60A`, so
the letters match the title box. The default stays "Giống cảnh": no video changes until it is picked.
The outlined scenes remain the opt-in the entry below describes, including its readability caveat.

## 2026-11-01 — Cloudflare Workers AI added as a second AI image provider

Gemini stays (for when the team has a paid plan) and Cloudflare Workers AI is added beside it; the image job's
provider is chosen with `IMAGE_GEN_PROVIDER` (`gemini` by default, so nothing changes until it is set to
`cloudflare`). The 2026-10-31 Gemini entry still holds. Reason: Gemini's free tier in practice gives no image
quota, while Cloudflare Workers AI's free allowance (10,000 neurons a day on every plan, Workers Free included)
covers about 57 FLUX.1 schnell photos a day, plenty for 1–3 videos, and the account is already used for the web.

Consequences: Cloudflare's FLUX.1 schnell ignores width/height and answers a 1024×1024 square, which
[imagegen.py](../api/src/reels_api/imagegen.py) cuts at the centre to 9:16 before storing; Gemini's frames are left
as they are. FLUX.1 schnell is Apache-2.0 and its photos carry no SynthID. Each provider has its own key on
Cài đặt › Nguồn tư liệu ("gemini", "cloudflare"); the Cloudflare account ID stays in `.env`.

## 2026-11-01 — Stock and AI-image keys can be pasted in the app; text colour and "no box" presets

Owner's request after the presets round. Cài đặt › Nguồn tư liệu takes the API keys of Pixabay,
Pexels and Gemini (AI photos), stored encrypted like the LLM keys
([source_keys.py](../api/src/reels_api/source_keys.py)); a key saved there wins over the `.env` one,
and with none saved the `.env` key still applies, so existing servers keep working. This extends the
2026-11-01 entry below that kept these keys in `.env`.

The text box gains a fifth style, "Không hộp" (outlined letters, no box), and a text colour
(Theo kiểu, Trắng, Đen, Vàng, Đỏ). The owner asked for both, knowingly reopening the MVP's rejection
of outlined text as hard to read on bright photos: it is an opt-in choice, the default stays the
yellow box, and the outline is thick (9% of the font size). Colours too faint on a box (white or
yellow on the yellow and white boxes, black on the dark box, red on the red box) are not offered and
fall back to the box's own colour in the renderer; marked words always keep a colour that differs
from the text.

## 2026-11-01 — Video presets, narration captions and stock clips

Built on the roadmap entry below. The render core takes per-video presets
([options.py](../worker/src/reels_render/options.py)): transition (fade, cut, slide), photo motion
(zoom in/out, pan, static) and its strength, four text box palettes, narration level, music ducking,
and captions. The defaults build the same FFmpeg filter graph as before, and a video's MP4 is flagged
outdated only when one of its presets differs from them. Narration voice and speed are per video
(any voice of the ElevenLabs account; speed 0.9/1.0/1.1), and the speed joins a narration's
signature only when not normal, so no existing MP3 is made again.

Captions time each word by an estimate spread over the measured narration (Vietnamese words are
single syllables of similar length) instead of ElevenLabs' `/with-timestamps` endpoint: switching
the endpoint would change how every narration is bought and stored, and is a later step if the
estimate drifts visibly. Captions are shown on content scenes only, never on the title scene, so
the first frame stays the thumbnail.

Stock video clips come from Pexels and Pixabay (the keys already used for photos) in the picker's
"Video" mode and are stored like uploaded clips: jobs still never pick photos or clips. The team can
turn any stock source off on Cài đặt › Nguồn tư liệu; keys stay in `.env`.

## 2026-11-01 — Scripts can be written by any of several LLM providers; their API keys are entered in the app

Owner's request, adapted from MoneyPrinterTurbo's LLM settings. "Cài đặt › Mô hình AI" (`/settings/ai`)
lists a fixed set of providers — Claude (Anthropic), OpenAI, Google Gemini, DeepSeek, OpenRouter, Groq,
xAI Grok, Qwen, Ollama and one custom OpenAI-compatible slot — each with its API key, base URL and model,
and one provider is chosen for the whole team (script and clone jobs). Two connectors cover them: the
Anthropic SDK for Claude, and the OpenAI-compatible `/chat/completions` for every other one. Every job
records the provider and model it wrote with, shown on the video page and in the job log, because other
models may follow the Vietnamese and the safety rules less well and reviewers should know.

The API keys are typed into the app and stored in the database, **encrypted like Fanpage tokens** with
the key in the storage folder (owner's choice, "option A"). This is an exception to "Secrets stay in
`.env`" for keys members manage on the Cài đặt pages; deployment secrets stay in `.env`. A key never
comes back in a response, only its last four characters. With nothing set on the page, Claude keeps
using `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` from the environment, so existing deployments behave as
before. The provider in use cannot lose its key or model, and "Kiểm tra kết nối" only lists the
provider's models, which costs no tokens. The output format stays code and the same for every provider.

## 2026-11-01 — Settings roadmap: team defaults for new videos, and the template opens up

Owner's decisions for the settings work adapted from MoneyPrinterTurbo (voice, music, transitions,
motion, text style and captions, stock clips), recorded now so later rounds follow them:
team defaults on the Cài đặt pages apply only to **videos created afterwards** — each video keeps its
own copy, changeable on its "Thiết lập" tab (a clone takes its source's), so changing a default never makes an old video render
differently; and the MVP's "one fixed template" rule is lifted for named presets (text-box styles,
transitions, motion), never free colour or size sliders. The video editor's side column became three
tabs (Xuất bản, Thiết lập, Nội dung đăng) and "Render" moved to a bar stuck to the bottom of the screen
to make room for them.

## 2026-11-01 — "Tìm ảnh khác" can search any stock source

Replaces the "What does not change" part of "The picker offers three stock sources" (below) for
the button only: "Tìm ảnh" / "Tìm ảnh khác" still searches Pixabay by default, and an arrow menu
next to it switches the scene's button to Pexels or Openverse (only the sources the api offers).
Each source reads the keyword list in the language it indexes, as the picker does. Owner's
request: Vietnamese dishes are thin on Pixabay, and opening the picker for every retry was slow.
The render core CLI stays Pixabay-only and jobs still never pick stock photos.

## 2026-10-31 — AI photos for missing scenes come from Gemini, stored like any chosen photo

The provider left open in `docs/specs/ai-scene-images/brief.md` is settled: Gemini image
generation via Google AI Studio (the owner's choice — free tier for testing, strong
Vietnamese prompts, native 9:16 output; model `gemini-2.5-flash-image` by default,
`IMAGE_GEN_API_KEY` / `IMAGE_GEN_MODEL`). This extends, and does not reverse, the rule
that a server render only uses a photo already stored on its scene: a new `image` job
(the video page's "Tạo ảnh AI cho cảnh thiếu") generates a photo only for scenes that
have neither a photo nor a clip, validates the bytes like an upload, and stores it with
`image_source` = `ai:<model>`. Photos and clips members chose are never overwritten.
A prompt Gemini refuses fails only its scene (the reason stays on the scene); a
provider-wide failure (no key, quota) fails the job, keeping the scenes already done.
Generated photos carry SynthID, so platforms may label the posts as AI-generated —
accepted, because the platforms state the label itself does not reduce distribution;
the mitigations are human review of every scene and mixing AI photos with stock and
uploads, not hiding the label.

## 2026-10-31 — Scripts write stock keywords in two languages

A scene now carries `keywords` (Vietnamese) and `keywords_en` (English). The Western stock
libraries index in English, so "Tìm ảnh khác" and the picker's Pixabay/Pexels tabs search the
English list first; Openverse, whose photos are community uploads often titled in Vietnamese,
uses the Vietnamese list. Each list falls back to the other when empty, so videos scripted
before this change keep working. Found while testing locally: with only Vietnamese terms,
Pixabay answered hyper-local dishes ("rau rút", "gà nguội") with loosely matched junk, and
find-image took the first hit blindly.

## 2026-10-31 — Openverse may use a registered OAuth application, anonymously by default

Openverse needs no key, and anonymous stays the default. If `OPENVERSE_CLIENT_ID` and
`OPENVERSE_CLIENT_SECRET` are configured, the client exchanges them for an access token
(client-credentials flow, cached in memory until shortly before expiry) for the registered
rate limits. Any failure in that exchange falls back to an anonymous search: a picker search
must never break because authentication did.

## 2026-10-31 — The picker offers three stock sources; Openverse is public-domain only

Extends "The web editor offers Pixabay photos again" (below). The picker (now "Chọn từ kho
ảnh") switches between Pixabay (the default), Pexels (vi-VN locale, portrait orientation;
hidden until `PEXELS_API_KEY` is set) and Openverse (no key). Vietnamese dishes are poorly
covered by Pixabay alone, and Openverse aggregates Flickr/Wikimedia photos uploaded by
Vietnamese users. Openverse is limited to CC0 and public-domain-mark works — filtered in the
query and again on each result's own license — because the channel earns money and the app
shows no attribution anywhere. A photo chosen from any source passes the same revalidation
and is stored with the scene exactly like a Pixabay one. What does not change: the quick
"Tìm ảnh" button and the render core CLI still use Pixabay only, and jobs still never pick
photos. Brief: [specs/stock-picker-sources/brief.md](specs/stock-picker-sources/brief.md).

## 2026-10-31 — Scripts write photo keywords again

The script output format asks Claude for `keywords` on every scene and `title_keywords` for
the title scene again (2–4 Vietnamese terms, most specific first), as the original tool did.
The parser and the save path never stopped reading them; only the format had dropped them,
which left every new scene without keywords and made "Tìm ảnh" and the picker start empty.
The format is code, not prompt data (see "Prompt text is app data, the output format is
code"), so the restoration lives in `claude.py`'s `OUTPUT_FORMAT` and its worked example.

## 2026-10-31 — The web editor offers Pixabay photos again; the render still uses stored photos only

Replaces the part of "Server renders use member-uploaded scene photos only" (below) that said the
web UI no longer offers stock search. Owner's decision, phase 1 of
[specs/ai-scene-images/brief.md](specs/ai-scene-images/brief.md): uploading every scene photo by
hand was the slowest step of making a video. Each scene card (title included) has "Chọn từ
Pixabay" (a grid of results for a keyword) and "Tìm ảnh" (the next result for the scene's saved
keywords), plus the "Từ khóa tìm ảnh" field, because the script no longer writes keywords. What
stays: a Pixabay photo is downloaded by the api and stored with the scene like an upload, so the
member sees and can replace it; the render uses only stored photos and still blocks a scene
without one; jobs never pick photos; no source or license info beyond the stored Pixabay URL.

## 2026-10-31 — Caption length comes from the editable prompt

The fixed output format no longer sets 80–120 words or a repeated full list, so a topic group can
ask for a short caption on `/knowledge` without a code change. With no request in the prompt, the
caption is short. The output format still fixes the JSON field and the 5 hashtags.

## 2026-10-31 — Narration reads the on-screen text, then the voice text

The spoken text is joined when the render runs rather than copied into the voice text, so choosing
another title or editing a scene's text is always what gets read. An empty voice text still means a
silent scene. Claude's voice texts got shorter and no longer repeat the screen, and the 120-word
budget now counts both, to keep a video under 48 seconds.

## 2026-10-31 — Decisions are logged in the repo

Settled decisions are recorded in this file, in the repo, because agents and team members can
only read the repo — not anyone's chat history or memory. The rules for every agent live in one
place, `AGENTS.md`; `CLAUDE.md` only imports it.

## 2026-10-31 — Own repository, not a fork of MoneyPrinterTurbo

The pipeline stages follow MoneyPrinterTurbo (MIT, attribution kept in adapted files), but this
is its own codebase: MoneyPrinterTurbo has no auth, no database and no scene model, carries many
unused providers and OAuth flows, and uses stock video clips instead of member photos.

## 2026-10-31 — The job queue is the Postgres `jobs` table, not Redis

At 1–3 videos a day a separate queue service is not worth running. Long work (Claude calls, TTS,
renders, Facebook posting) never runs in the API process; the worker runs it.

## 2026-10-31 — One worker only; a dead worker's job is never re-run automatically

The worker holds a Postgres advisory lock for its whole life, so exactly one worker takes jobs.
A job still marked running when a worker starts belonged to a worker that died: it becomes
failed ("Worker khởi động lại giữa chừng") and a member retries it by hand. Auto-rerunning could
spend Claude or ElevenLabs credit without anyone deciding to.

## 2026-10-31 — Rendering is a native FFmpeg filter graph; no MoviePy, no Remotion

MoviePy composites frames in Python and is the speed bottleneck. Remotion needs a paid Company
License for teams of four or more. Pillow pre-renders text boxes as transparent PNGs and FFmpeg
does the compositing (`zoompan` for Ken Burns motion, `overlay` for text).

## 2026-10-31 — Server renders use member-uploaded scene photos only

Every scene photo or clip is uploaded by a member while editing, so the render uses exactly what
the preview showed; a scene without one blocks the render. Stock search (Pixabay) exists only in
the render core's CLI path — the web UI no longer offers it and jobs never pick photos. No source
or license info is stored for stock photos (owner's decision).

## 2026-10-31 — Narration is ElevenLabs "Adam" on `eleven_v3`, stored per scene and reused

`eleven_multilingual_v2` does not speak Vietnamese, so the model is `eleven_v3` with
`language_code: vi`. Narration is paid per character, so each scene's MP3 is stored and re-made
only when its text, voice or model changes.

## 2026-10-31 — Fanpages are connected by pasting a Page token; there is no OAuth flow

A user or system user token is swapped for each Page's own token through `/me/accounts`, and that
token is what is kept — stored encrypted with a key that lives in the storage folder, so a
database dump alone does not reveal it. Losing the key file only means pasting the tokens again.

## 2026-10-31 — A video is never posted to Facebook twice

The reel's id and its MP4 are saved before the upload, and the moment Facebook is asked to
publish is saved before asking. A retry reads the reel's status first, because an attempt may
have reached Facebook whatever it reported. Scheduling uses Facebook's own scheduling; the app
has no posting timer.

## 2026-10-31 — Sessions are database tokens, not JWTs; users are disabled, never deleted

Sessions are opaque random tokens stored hashed in Postgres and last 30 days, sliding. Disabling
a user, forcing a password change and signing out every device then take effect immediately.
There is no self-signup and there are no roles: every member can manage users.

## 2026-10-31 — Prompt text is app data; the output format is code

Members edit the script and clone prompts and the banned words on `/knowledge`. The JSON output
format and its worked example stay in code (`claude.py`), so an edited prompt can never break
the parsing every job depends on.

## 2026-10-31 — Banned words warn, they never block the render

A banned word in the title scene, a scene, the caption or the pinned comment shows a yellow
warning only. Softer wording ("hỗ trợ", "tốt cho") is preferred over sensational claims, because
Meta flags or demonetizes medical wording even when the fact is true.

## 2026-10-31 — Affiliate products are approved by fixed rules

A product becomes approved only with a trusted shop type, at least 4.7 stars, at least 100 sales
and no banned word in its name. Editing an approved product sends it back to draft. The list is
entered by hand from the affiliate dashboard; there is no Shopee API call yet (see
[backlog.md](../backlog.md)).

## 2026-10-31 — Production: Coolify for api, worker and Postgres; Cloudflare Workers for web

The web app needs a server runtime for `proxy.ts` and the `/api/*` rewrite, which Cloudflare runs
through OpenNext on Workers (the Pages adapter is deprecated). Coolify auto-deploy stays off:
only CI deploys, after every test passes, api first (it runs the migrations), then the worker,
then the web.
