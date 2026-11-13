# 2026-11-13 — A video goes to TikTok by itself when it goes live on Facebook

Asked by namtc, 2026-11-13 ([brief](../specs/tiktok-auto-post/brief.md)): at the Facebook slot (07:00, 11:00, 18:00) the
same video reaches the member's TikTok inbox as a draft, with no click on the TikTok card. Direct (public) posting is
built in the same change but is not the behaviour yet.

- **What:** `jobs.queue_tiktok_posts`, called by the worker's one-minute round next to `queue_post_checks`, finds the
  Facebook posts (`scheduled` or `published`, a video, slot passed) and, for each, creates a TikTok `Publication` and a
  `tiktok_publish` job the existing worker code runs (`tiktok_publish.run`: draft or direct, caption, AIGC label). A
  draft reaches the inbox about one minute after the slot, one worker round; nothing in the app promises seconds.
- **Gates (all must hold):** the video has an MP4 and no active job (the next round retries), no TikTok post of it
  that is `pending`, `scheduled` or `published` (a `cancelled` one does not block; a draft sent by hand is never
  doubled), the Page has an owner and a linked TikTok account that is active, a TikTok one, and its owner's. Facebook
  approval still gates everything: a video never scheduled on Facebook gets nothing, and a Page with no TikTok
  account (Già Mà Khỏe) gets nothing. Articles are never swept.
- **Mode on the Page:** `fanpages.tiktok_auto_mode` (`draft` by default, `direct`), set by the Page's owner
  (`PUT /fanpages/{id}/tiktok-auto-mode`) under the TikTok account select. It lives on the Page, not the topic group,
  because the TikTok account is already linked per Page and a group may be posted by several Pages. `direct` posts with
  `PUBLIC_TO_EVERYONE` (never the job's `SELF_ONLY` default) and only works once TikTok has reviewed the app (In review
  today); until then the job fails with TikTok's message.
- **Added to the brief:** only slots of the last 24 hours are swept (`TIKTOK_SWEEP_WINDOW`). Without it the first
  round after deploy would send a TikTok draft for every video ever posted on a Page that has an account linked.
- **Limits:** a draft carries no caption and the TikTok Shop cart cannot be attached through the API in either mode;
  the member does both in TikTok's app.
- **Rejected:** a delayed TikTok job at the slot (`Job` has no run-at, jobs start at once); a TikTok timer apart from
  the worker round (a second clock to keep alive); one mode per topic group.
