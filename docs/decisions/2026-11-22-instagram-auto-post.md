# 2026-11-22 — Instagram follows Facebook at the slot, switched per Page

Asked by the team on 2026-11-22 ([brief](../specs/instagram-auto-post/brief.md)): a video that goes live on a Page's
Facebook at its set time is also posted to the Page's Instagram, without ticking Instagram on every video. This
**reverses** the "Not in this round" of [2026-11-19 Instagram posting](2026-11-19-instagram-api-posting.md) (and §5 of
its [brief](../specs/instagram-posting/brief.md)): "no Instagram in a Page's queue, no auto-post at the Facebook slot
like TikTok".

1. **Same pattern as TikTok auto**, not a hook in the Facebook publish route: a worker round
   (`jobs.queue_instagram_auto_posts`, next to `queue_tiktok_posts`) reads the due Facebook posts and makes the
   Instagram post. The round sees every way a post is scheduled (the "Đăng bài" panel, a Page's queue, a browser-set
   job, the MCP `schedule_video`).
2. **A switch per Page, off for every Page** (`fanpages.instagram_auto`, migration 0117). Instagram has no draft, so it
   is on or off, not a mode. A Page with no linked Instagram account cannot be switched on; only its owner flips it.
3. **Instagram goes about a minute after Facebook**: Instagram's API has no scheduled time, so the minute round is the
   clock, as for a hand-scheduled Instagram post.
4. **Only a scheduled Facebook post triggers it**; "Đăng ngay" does not (it has no slot), as for TikTok auto.
5. **24-hour window** (`TIKTOK_SWEEP_WINDOW`): an older Facebook post is not sent late, so switching on does not flood.
6. **No new permission, token or connection**: the Page's stored token and the account read at each Page check. No
   Instagram numbers or comments in this round.
7. **A failed Instagram post is not retried by the round**: a video with any Instagram post but a cancelled one is left
   alone, so an error that repeats (a token without `instagram_content_publish`) does not make a post and a job every
   minute for 24 hours. The member presses "Thử lại". Differs from TikTok auto on purpose.
8. **One MP4 goes to one Instagram account once** (as in 2026-11-19): the check does not look at the Page, so two Pages
   switched on with different accounts post it only through the one the round reaches first. The caption is the
   video's, as in the manual route, so it can differ from a Facebook post text edited at posting time.
9. **No length filter**: Instagram took a 113-second reel through its API on 2026-11-22; the code adds no limit.
10. **First round only for Tiệm Đọc Comment**, once its token has `instagram_basic` and `instagram_content_publish`
    (the owner's manual step after merge). The other Pages stay off until their owners decide.

**Rejected:** hooking into the Facebook publish route (misses the queue); retrying a failed Instagram post by itself;
posting a Facebook post older than a day.
