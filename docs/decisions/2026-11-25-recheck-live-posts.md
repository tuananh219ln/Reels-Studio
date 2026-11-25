# 2026-11-25 — A live post is checked again for deletion, on Facebook and on Instagram

A reel or Instagram Reel deleted on the platform after it went live stayed "Đã đăng" for good: Facebook's one automatic
check ran only once, after the scheduled time, and Instagram's numbers reading only logged a failure. Only YouTube and TikTok
found a removed video by themselves (`metrics._missing`).

- **Schedule** (`metrics.recheck_due`): a `published` post is checked again when its last check is older than its age asks
  for: every 6 hours in its first 3 days, daily up to 30 days, weekly after; never checked is due now. A deleted post and one
  set aside ("Bỏ qua", `match_status = ignored`) are not checked by themselves; "Kiểm tra" still works on a deleted one.
- **Facebook**: the same `check` job as the one after the scheduled time (`jobs.queue_post_checks`), at most 5 queued or
  running at once, so the first round after this shipped (every old post is "never checked") cannot flood the worker, and a
  video with another job waits for the next round. The rule of [2026-11-13](2026-11-13-unreadable-is-not-deleted.md) is
  unchanged: only a 404, or a 400 (#100) while the token still reads another reel of the Page, means deleted.
- **Instagram**: read directly by the worker, 3 per round, no job (`metrics.check_instagram_due`, `instagram.media_gone`),
  like its numbers. It follows the same rule: a media answer of 404 or 400 (#100) means deleted only while the token still
  reads the account's media list; any other failure leaves the post as it was.
- **Shown**: the video page's post rows say when the post was last checked and, for a post gone from Instagram, since when.

The cost: a post is shown as posted for up to 6 hours (a new one) after it is deleted on the platform; "Kiểm tra" is still
the way to know at once. A Page with a single posted reel still cannot learn that this reel was deleted (no witness).
