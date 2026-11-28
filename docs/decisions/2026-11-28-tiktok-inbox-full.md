# 2026-11-28 — A full TikTok inbox pauses that account's drafts for a day

Asked by namtc, 2026-11-28, after two Telegram notices "Đăng TikTok không thành công — TikTok báo lỗi:
spam_risk_too_many_pending_share" at the 11:00 and 11:30 slots.

- **Cause:** not a bug in the app. In draft mode ([auto post](2026-11-13-tiktok-auto-post.md)) every Facebook slot sends
  a draft into the TikTok inbox, and TikTok keeps only about 5 drafts waiting per account; a Page with 5 slots a day
  (or several Pages on one TikTok account) fills it as soon as the member does not finish drafts in TikTok's app.
- **What:** the error is translated (`tiktok.INBOX_FULL`): the inbox is full, post or delete the waiting drafts in the
  TikTok app, press "Thử lại", and drafts to this account stop for 24 hours. It reaches the Page's owner through the
  existing private Telegram failure notice, never the team group.
- **Pause:** `jobs.queue_tiktok_posts` skips draft mode for an account with an `INBOX_FULL` failure in the last 24 hours
  (`TIKTOK_SWEEP_WINDOW`), unless a draft job of that account succeeded after it (the member emptied the inbox and
  pressed "Thử lại"). Read from the jobs table: no new column, no migration. Direct posts are not paused (they do not
  go to the inbox).
- **Narrows** the 2026-11-13 auto-post decision: a video whose slot passed during the pause gets no TikTok draft by
  itself (the 24-hour sweep window has mostly closed by then); the member can still send it from its TikTok card.
- **Rejected:** counting our own drafts per account to stay under 5 (the API cannot tell whether the member already
  finished a draft in the app, so the count would block drafts needlessly).
