# 2026-11-23 — Instagram numbers on a Page's dashboard

Asked by the owner (namtc) on 2026-11-23: the Page dashboard had no Instagram side. This is the "Instagram's numbers"
of [2026-11-19 Instagram posting](2026-11-19-instagram-api-posting.md)'s "Not in this round", now wanted. It reverses
that line only; nothing else of it changes.

- **Account numbers first.** `instagram_insights` (migration 0119) keeps, per Page and Vietnam day, views, reach,
  interactions and follows, read by the Page check (every 12 hours, the last 7 days rewritten, Instagram's data lags
  up to 48 hours). `GET /api/fanpages/{id}/instagram-dashboard` totals each period against the one before, as the Facebook
  one does; a day with no number is null, never 0.
- **Needs `instagram_manage_insights`** on the Page's token (Meta's Facebook-Login permission for Instagram insights).
  The app cannot ask for it: the Page's owner pastes a new token that has it. Until then the dashboard says so and the
  Page stays "Hoạt động": a missing permission is not a broken connection, as for `read_insights`.
- **One day at a time.** `views`, `reach` and `total_interactions` are asked with `metric_type=total_value` over a one-day
  window, so a day's number is its own total; `follower_count` comes per day in one call. About 22 calls per check per
  Page with an account; a permission refusal stops at the first.
- **Switch, not a second page.** The Page's dashboard gets "Facebook | Instagram", the tabs being "Tổng quan" and the
  shared "Lịch đăng"; the same figure tiles and chart. Hidden when the Page has no linked account.
- **Not in this round** (still to do, each its own change): "Nội dung" (per-Reel numbers: views, reach, likes, comments,
  shares, saves, average watch time, measured at 24 and 48 hours like Facebook's), "Đối tượng" (gender, age, city; Instagram
  gives these only from 100 followers), and the Reels in the "Lịch đăng" tab.
- **Not verified against Meta's live API** (no real calls in development, AGENTS.md): the metric names and the
  one-day `total_value` shape follow Meta's documentation; the first real read of a Page with the permission must be
  looked at before the numbers are trusted.
