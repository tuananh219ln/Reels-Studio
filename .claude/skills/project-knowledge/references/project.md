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

1. **Team login:** accounts are created by members. There is no self-signup.
2. **Knowledge Base:** editable channel documents and a food bank with sourced benefits. Claude
   drafts the content; food bank rows need a member's approval before use. See [content.md](content.md#knowledge-base).
3. **Script generation:** one Claude call turns a topic into 5 title options, a 5–7 scene script,
   a caption with hashtags, per-scene image prompts, affiliate suggestions, and a safety self-review.
   Every part is editable.
4. **Scene images:** members upload their own photo per scene. When a scene has no photo, the app
   searches stock images by keyword.
5. **Templated render:** a fixed visual template, Ken Burns motion, background music from the team
   library, and Vietnamese TTS. TTS is on by default and can be turned off per video.
6. **Job log:** shows status and duration, offers the MP4 download, and can re-run a job.

---

## Development Phases

1. **MVP:** the features above.
2. **Assisted publishing for Reels and TikTok:** a schedule, a reminder at the posting windows (see
   [content.md](content.md#monetization-and-publishing-context)), and a ready package of MP4, caption, and hashtags. Members post and pin the affiliate
   comment manually.
3. **Later, in no fixed order:** topic calendar, 48-hour metrics tracking, winner variants, API
   auto-posting, YouTube Shorts, English content, the disclaimer and functional-food sentence, and
   AI image generation. Concrete items live in [backlog.md](../../../../backlog.md).

API auto-posting is deferred for these reasons:

- Instagram publishing needs a Business/Creator account linked to a Facebook Page.
- Until the TikTok Content Posting API app passes audit, it can only post privately.
- Neither platform's API can pin a comment.

---

## Out of Scope

- Public users, self-signup, roles, or permissions.
- Multiple channels or niches with separate prompts and templates. MVP serves one niche, and its
  prompt is stored as editable configuration.
- Editing videos in CapCut or exporting CapCut projects.
- Using Facebook/CapCut music libraries. They are not accessible outside those apps.
- Automatic posting, metrics, and analytics in the MVP.
