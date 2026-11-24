# 2026-11-24 — Winner flag back, "Cửa đo 48h", group documents, one "Lịch đăng", one status name

Asked by the owner (via the FoodDose brief of Muse); the owner agreed to reverse "Video thắng is dropped" and to do it all in one PR.

- **Reverses** 2026-11-03 "Video thắng is dropped". A post is a **winner** at `analytics.WINNER_TIMES` (10) × its Page's 60-day
  median at 48 hours or more, from 5 measured posts (`MIN_SAMPLES`). It is worked out when shown (`is_winner` in
  `analytics.of_post`), **never stored**, as 2026-11-04 required; no weekly count or filter comes back. Issue #44's
  trigger is this flag: the group's video list shows "Winner" and "Tạo 3 biến thể".
- **"Tạo 3 biến thể"** (`POST /api/videos/{id}/variants`, `duplicate.variant_drafts`): three draft copies of 2026-11-14
  "Nhân bản y hệt", named "(biến thể 1: đổi hook)", "(… 2: đổi 1–2 món)", "(… 3: đổi dạng)". **No AI call** (the brief
  forbids paid APIs); the name is the brief for whoever edits it (a member, or an assistant through MCP). Chosen over
  rewriting each copy by the team's AI.
- **"Cửa đo 48h"** (`GET /api/fanpages/{id}/gate`, `page_dashboard.gate`), on every Page, above its tabs: median views
  (the Page's 60-day median, as everywhere), median share/view, best 48-hour views, videos measured at 48 hours
  towards 14 and 30, and the state: pass (median > 1,000 and a video > 10,000, from 5 measured), change hook and pillar
  (30 measured, median < 500 and share/view < 0.1 %), hold, or still measuring. The thresholds are constants of
  `page_dashboard.py`, the same for every Page, not FoodDose's alone. Its share/view (0.1 %) is the gate's; the team's
  goal elsewhere stays 0.2 % (`analytics.SHARE_GOAL`).
- **Documents** ("Tài liệu" tab, `topic_docs`, migration 0124): the Markdown of how a group's Page is run; **the copy in the
  app is the master**, a file on a member's machine only a draft. Anyone reads; writing follows "Cho cả đội sửa". MCP
  `list_docs` and `get_doc` (`reels:read`) let the daily job read the rules instead of pasting them. Version history was
  not built (who and when last changed it only). A document is rules to follow, so whoever may edit the group steers the
  job that reads it: turn "Cho cả đội sửa" off to limit it to the maker.
- **One "Lịch đăng"**: the two tabs did not share a source (the group's tab read `/api/posts` filtered by group; the
  Page's read the dashboard and the queue). The group's tab is now only a link to each Page of the group; the Page's tab
  on Quản lý kênh is the calendar.
- **One status name**: "Đã hẹn giờ" (the name of the action "Hẹn giờ", already used by articles, the video status card
  and the Page's strip) replaces "Đã lên lịch" everywhere (video lists and filters, plan statuses, article plan slots,
  the Page's strip and queue). "Chờ đăng" is a rendered video not yet scheduled; "Đã đăng" is posted.
- **The 30-day plan already is the real calendar** (ideas on days, the n-th idea at the n-th posting time, status read
  from the video and its posts), so no second schedule was built from `lich-dang-7-ngay.md`: import it as plan ideas.
  An empty posting time of a day is a dashed button that adds an idea there.
- **Prompt warning** now says no web AI video without a script prompt, while MCP and hand-written scripts still work
  (`mode: manual` never needed the prompt). Saving FoodDose's prompt is a member's entry in the app.
- Every number on Quản lý kênh names its source and period (Facebook / Instagram / Tool, N ngày).
