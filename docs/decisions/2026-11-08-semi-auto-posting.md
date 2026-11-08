# 2026-11-08 — Semi-automatic posting: the worker prepares today's ideas, the Page's owner approves, then it posts

Brief [docs/specs/semi-auto-posting](../specs/semi-auto-posting/brief.md), approved by the owner (namtc) with his answers
on the review of 2026-11-08: preparing at 08:00 by default, approval in the plan's "Hôm nay" strip, "Không duyệt"
leaves the video to be fixed by hand.

- **A round of the worker, not a scheduler** ([auto_runs.py](../../api/src/reels_api/auto_runs.py)), beside the
  queue's: it only queues the jobs a member could (script, photos, render, clone, publish, tiktok_publish) and reads
  how they went. One run per idea and day (`auto_runs`, unique), so a second round never makes a second video; a day
  without an idea makes nothing and says "Hôm nay chưa có ý tưởng trong kế hoạch". A Page is checked once a day:
  ideas added after its preparing time wait for the next day.
- **Never posted unapproved**, and only the Page's owner approves, in the app; MCP only reads. This is the first time
  the app writes a script nobody pressed for: on the team's LLM, paid (the owner's choice: a member's own Claude
  through MCP needs someone chatting), about one call per Page and day, plus its narration.
- **The render rule stands**: with the render machine switched on (2026-11-07) a run waits for it ("Đang chờ máy
  render") and never falls back to the VPS.
- **Approving** schedules the post at the idea's time, the Page's own posting times first, as its queue reads them;
  too late or taken, its next free time within 48 hours. The affiliate comment follows as for any post.
- **TikTok**: a Page names one of its owner's TikTok accounts (`fanpages.tiktok_account_id`), as a connection is a
  member's, not a Page's; the draft is the Facebook MP4 (2026-11-08, "One MP4 goes to every platform"), or with
  "Bản TikTok riêng" (off by default) a clone made as "Tạo bản TikTok". It is sent once the publish job is done,
  since a video holds one job at a time. No account, an expired connection or "Bỏ qua TikTok" posts Facebook only.
- Banned words only flag the run, as they only warn (2026-10-31).
