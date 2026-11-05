# Project Context

## Project Overview

**Name:** Reels Studio

**Description:** Internal web app that turns a topic into a ready-to-post 20–40 second vertical
(9:16) short video for Facebook/Instagram Reels, TikTok, and YouTube Shorts.

The first channel is a Vietnamese faceless "health leaflet" channel (dưỡng sinh / dinh dưỡng for
people 40+). The content formula, knowledge base, and safety rules are in [content.md](content.md).

---

## Target Audience

**Primary users:** The owner and an internal team of about 5 people. All members have equal
permissions and share one video library. The app is never public.

**Use case:** Produce 1–3 short videos per day, either from a topic calendar or by cloning last
week's winning video with a changed food, age milestone, or number.

---

## Core Problem

The owner has little time for ideation and editing. The manual workflow takes about 30 minutes per
video: pick a topic, write the script with a Claude Project prompt, check the content, find images,
edit in CapCut, post and pin the comment, then record metrics after 48 hours. Reels Studio automates
scripting, image assembly, and rendering. Assisted publishing and tracking come in later phases. The
app replaces CapCut, so the output is a finished MP4.

---

## Key Features (MVP)

1. **Team login (built):** email and password; accounts are created by members (the first one by
   a CLI command). There is no self-signup and no roles: every member can manage users. Google
   login is planned ([#54](https://github.com/tuananh219ln/Reels-Studio/issues/54)).
2. **Knowledge Base (partly built):** today `/knowledge` holds the editable script and clone
   prompts, the banned words and each group's 30-day topic plan (3–5 video ideas a day, each with
   the viewer's pain and a hook angle; imported, written by AI or typed in, and used by "Tạo video"). Planned: editable channel documents and a food bank with sourced
   benefits, drafted by Claude, with food bank rows needing a member's approval before use. See
   [content.md](content.md#knowledge-base).
3. **Script generation (built):** one LLM call (Claude by default; another provider can be chosen
   on Cài đặt › Mô hình AI) turns a topic into 5 title options, a 5–7 scene
   script, a caption with hashtags, per-scene image prompts, affiliate
   suggestions, a safety self-review, and music suggestions. Every part is editable. "Nhân bản"
   writes one variant of an existing video from a change request. "Tự viết" makes a video without
   the AI: a member pastes a script (one scene per paragraph) or writes it on the video page, with
   no AI cost and no AI safety review.
4. **Scene images (built):** members give every scene a photo or clip: their own upload, or a
   Pixabay photo picked from a grid or found by the scene's keywords and stored with the scene; a
   scene without one blocks the render.
5. **Templated render (built):** a fixed visual template, Ken Burns motion, rendered on the server.
   Narration in the ElevenLabs "Adam" voice reads each scene's voice text, or its on-screen text when
   that is empty (on by default, off per video). Music is optional: one MP3 per video, uploaded or picked from the team music library (tracks
   tagged by fixed topics and a mood).
6. **Affiliate (built):** the team's list of Shopee and TikTok Shop products, each platform with
   its own approval rules, ranked by expected commission. Each member adds their own affiliate
   accounts, which nobody else sees. With a Shopee account (Open API App ID and Secret), the
   worker searches Shopee for the script's product ideas and a member picks from the results;
   each Page gets its owner's own link, and the owner sees their orders by video and Page.
   Products are chosen on the video page (or on "Affiliate" after posting), and once a reel is
   live the worker writes the pinned comment with their links under it; members still pin it:
   Facebook's API cannot. A TikTok version of a video is its own video, posted by hand in
   TikTok's app with TikTok Shop's cart and recorded with its link.
7. **Job log (built):** every job with status, duration, AI call count, the model that wrote a
   script, and error; failed jobs
   are retried from the video page, where the MP4 plays and downloads.
8. **Facebook posting (built):** members connect Fanpages by pasting a Page token, then post a
   rendered video as a Reel now or at a set time, post a new render again, cancel a post not yet
   public and delete a public one from Facebook. "Bài đăng" lists posts on their way, failed (with
   "Thử lại"), posted, scheduled, cancelled and deleted under status tabs, and its "Lịch" view shows
   the posted and scheduled ones in a month, both in Vietnam time. The worker checks each Page's token twice a day (and on "Kiểm tra ngay"), so a
   broken one shows on "Quản lý Page" and in "Đăng" before a post fails, and keeps the Page's
   followers with this week's gain, and its views, reach and engagements by day from Page Insights.
   "Bình luận" gathers visitors' comments under the app's reels on every Page, to answer as the
   Page, hide or set aside. Opening "Quản lý Page", "Bài đăng" or "Bình luận" asks the worker
   to read again what it has not read in 15 minutes, so nobody has to press a button first.
   **Posting queues on "Quản lý Page"** (built): each Page posts one topic group at its own posting times, or the group's.
   A member adds a rendered video they have watched with "Thêm vào hàng chờ"; it goes to their own
   Page of the video's group, and the worker schedules the first video of each queue at the Page's
   next free time within 48 hours, through the usual publish job.
   **A dashboard per Page** (built, phase 1): a click on a Page's card opens `/fanpages/[id]`, like Facebook's
   Professional Dashboard: views, reach, engagements and new followers over 7, 28 or 90 days against the days
   before, daily charts with the days the app posted, the latest post's numbers, the week's scheduled posts and
   free times, and the Page's posting queue. Only numbers the app already reads are shown. A per-post content
   library ("Nội dung") and more Page Insights metrics are later phases.

9. **ChatGPT connection (built, opt-in):** private MCP tools read/search videos, edit scene and posting
   text, create script jobs and request renders. Members authorize and revoke OAuth connections
   on Cài đặt › Kết nối ChatGPT; see [chatgpt.md](chatgpt.md).
10. **Post numbers (built, issue #74 part 3):** the worker reads each public post's views, shares,
    comments and reactions from Facebook, daily for 14 days, and keeps its 48-hour numbers; "Bài
    đăng" shows them, sorts by views, compares each with its Page's median at 48 hours and shows the
    weekly KPIs. "Phân tích bài đăng" adds watch time, reach, replays, follows and the retention
    curve, split by the scenes of the posted MP4.

---

## Development Phases

1. **MVP:** the features above.
2. **Assisted publishing for Reels and TikTok** (Facebook Reels posting and its calendar are built): a schedule, a reminder at the posting windows (see
   [content.md](content.md#monetization-and-publishing-context)), and a ready package of MP4, caption, and hashtags. Members post and pin the affiliate
   comment manually.
3. **Later, in no fixed order:** topic calendar, 48-hour metrics tracking (built), API
   auto-posting beyond Facebook Pages (built), YouTube Shorts, English content, the disclaimer and functional-food sentence, and
   AI image generation. Concrete items are [GitHub Issues](https://github.com/tuananh219ln/Reels-Studio/issues).

Posting to connected Facebook Pages is built. The rest of API auto-posting is deferred for these reasons:

- Instagram publishing needs a Business/Creator account linked to a Facebook Page.
- Until the TikTok Content Posting API app passes audit, it can only post privately, and TikTok's
  guidelines do not accept a tool for a team's own accounts. Sending to the app's inbox, where a
  member finishes the post, is the likely route.
- Neither platform's API can pin a comment.

---

## Out of Scope

- Public users, self-signup, roles, or permissions.
- Multiple channels or niches with separate prompts and templates. MVP serves one niche, and its
  prompt is stored as editable configuration.
- Editing videos in CapCut or exporting CapCut projects.
- Using Facebook/CapCut music libraries. They are not accessible outside those apps.
