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
- **Per-Reel numbers** (the owner's second round, the same day): an Instagram Reel the app posted is read through its Page's
  token like the other platforms' posts, on the same schedule (hourly in the first 48 hours, then thinning), kept as
  snapshots (`raw.numbers` holds reach, saves, watch time), with no new column; "Nội dung" lists them.
- **Audience:** `instagram_audience` (shares of gender, age, city) is read at the Page check and kept when a later read
  gives nothing; under 100 followers Instagram refuses and the tab says why. **Facebook gets no demographics tab**: this round did not
  confirm which Page demographic metrics Meta still gives (it has retired Page metrics before: `post_impressions_unique` in
  2026-06), and the app does not add a metric on a guess. Facebook's "Đối tượng" stays followers.
- **"So sánh"** puts a video's Facebook and Instagram numbers side by side; **"Giờ đăng hiệu quả"** names the best hours from
  the Page's own posts (at least 6 posts a platform, 2 an hour, shown as a hint); **falling views** (half or less against
  the week before, both weeks ending two days ago for Instagram's lag) shows on the Page card. All three work for
  Facebook and Instagram.
- **Still to do:** the Reels in the "Lịch đăng" tab, and a comparison over time (a platform's share of the Page's views).
- **Not verified against Meta's live API** (no real calls in development, AGENTS.md): the metric names and the
  one-day `total_value` shape follow Meta's documentation; the first real read of a Page with the permission must be
  looked at before the numbers are trusted.
