# 2026-11-25 — "Thống kê" compares Pages; no grand total, no invented numbers

Asked by the owner (brief: [specs/stats-content-guides/brief.md](../specs/stats-content-guides/brief.md)); three things in one pull
request: the page "Thống kê", changes to a Page's "Nội dung" tab, and the menu entry "Tất cả hướng dẫn".

- **"Thống kê" (`/stats`) only compares Pages.** One row per Page; nothing is added up across Pages, and there is no "% growth"
  (Facebook's first period shows a false +100%): the previous period is shown as an absolute number. It sits in "Đăng và kiếm
  tiền" after "Bài đăng". The member's own Pages start picked (`mine`), a teammate's are one click away.
- **One request for all Pages**: `GET /api/stats` builds each row from the functions of the Page's own dashboard (no new
  numbers, nothing stored), so the page is one request, not about thirty, and a row always agrees with its dashboard.
- **Columns Facebook does not give are not shown**: unique viewers, impressions, watching for 1 minute, followers against
  non-followers, a Facebook audience. `reach` ("Tiếp cận") is the nearest number and is called that. Instagram's audience
  is shown for Instagram.
- **Periods are 7, 28 and 90 days** (the dashboard's), not 7, 14, 28 as in the first sketch.
- **"Nội dung" gets one new column, "Thời gian xem"** (all plays together, `post_video_view_time`, already read). The four
  others the brief asked for (saves, link clicks, viewers, impressions) are **not added**: Meta documents no such metric for a
  Facebook reel (saves and link clicks) or only reach (viewers, impressions), so a column and a migration would only show "—".
  Taken up again when a metric is found on a real Page's token.
- **Not in this pull request**: a Reels / Ảnh / Bài viết filter on "Nội dung" (an article's number is reach, a reel's is
  views, they do not share a unit) and the "Định dạng nội dung hàng đầu" section on the dashboard (same reason).
- **The "Nội dung" row has one "⋯" menu** instead of three buttons; the post drawer (analysis, comments, reel link) opens
  from it.
- **"Tất cả hướng dẫn" (`/guides`)** lists the guides of [2026-11-25-in-app-guides](2026-11-25-in-app-guides.md) by screen, in
  "Tài nguyên" after "Kho kiến thức"; each screen keeps its own "Hướng dẫn" button.
