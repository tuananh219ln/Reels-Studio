# 2026-11-14 — Posts are read on a schedule by age, with fixed marks; YouTube through its Data API ("Bài đăng" part 2)

Part 2 of the spec of [2026-11-14-posts-board](2026-11-14-posts-board.md) (§3.1, §3.3, §3.5, §3.6, §1.10). tuananh219ln
chose the spec's schedule over the daily readings of 2026-11-03 ([decisions.md](../decisions.md), "Post numbers: the
worker reads them between jobs, daily for 14 days"), which this replaces for the schedule only.

- **Still not a job**: the worker reads due posts between jobs (2026-11-03), a request never calls a platform.
- **The schedule** (`metrics.next_reading`): due as soon as live (not an hour after), then hourly to 48 hours, every
  6 hours to 7 days, daily to 30 days, weekly to 90 days, then never (was 14 days). The 1h, 24h, 48h, 7d and 30d
  marks fall on a reading. Up 50 % or 2.000 views since the reading before, in the first 48 hours: every 15 minutes.
  Facebook costs one Video Insights call per reading, about 50 per reel in its first two days at 1–3 reels a day.
- **Marks** (`views_1h` … `views_30d`): the reading within the tolerance after the mark, nearest it; past the
  tolerance with readings on both sides, the line between them, marked "ước tính"; else none ("n/a"). Set once.
  Facebook's `48h` row of `post_metrics` is still kept as before: the KPIs and the medians read it, unchanged.
- **A failed reading waits an hour** (was a day), for any platform.
- **Removed posts, YouTube only.** The spec's "not found twice an hour apart → removed" applies to YouTube, whose
  Data API leaves a deleted or private video out of its answer. It does **not** apply to Facebook:
  [2026-11-13-unreadable-is-not-deleted](2026-11-13-unreadable-is-not-deleted.md) found that a reel the token cannot
  read answers like a deleted one, so a reading never marks a reel removed; the check keeps deciding that.
- **YouTube** needs `YOUTUBE_API_KEY` (the team's, no OAuth; 50 ids per call, 1 of 10.000 free daily units). Without
  it YouTube posts are recorded but not read. Its `publishedAt` replaces the post's time unless the member typed one
  in "Dán link" or "Sửa". With the key, a pasted YouTube link's preview takes its time and length from the API, so the
  length part of the matching counts for YouTube.
- **"Cập nhật view" on the board** asks the out Facebook and YouTube posts of the videos shown (at most 200), once per
  5 minutes per member (`users.views_refreshed_at`, migration 0088); opening the page still asks the stale Facebook
  ones as before.
- **Not done here:** TikTok views (part 4), the Meta Suite import (part 3); "Nhật ký job" does not list readings (they
  are not jobs, as decided on 2026-11-03), so the spec's job log lines for `metrics.snapshot` are the worker's log.
