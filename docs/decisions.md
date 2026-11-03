# Decision Log

Settled product and technical decisions, each with a short reason, so every person and every
coding agent working on this repo knows why things are the way they are.

How to use: add a new decision as a new entry at the top, with its date. Never edit an old entry.
If a new decision replaces an old one, say so in the new entry. Agents read this file before
starting a new round of work and never silently reverse a logged decision (see
[AGENTS.md](../AGENTS.md)).

The entries dated 2026-10-31 were recorded retroactively: the decisions were already in effect
in the MVP and described across `docs/`; this log gathers them in one place.

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
