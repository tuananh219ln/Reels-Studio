# 2026-11-22 — YouTube follows Facebook at the slot, private, switched per Page

Asked by the team on 2026-11-22 ([brief](../specs/youtube-auto-upload/brief.md)): a video that goes live on a Page's
Facebook at its set time is also uploaded to the Page's YouTube channel, without pressing "Tải lên YouTube" on every video.

1. **Upload only, private.** The round makes the same post and `youtube_publish` job as the manual card; `privacyStatus`
   stays `private` (the Google app is not yet verified). The member makes the video public in YouTube Studio.
2. **A switch per Page, off for every Page** (`fanpages.youtube_auto`, migration 0118). It can be switched on only by
   the Page's owner, with a channel chosen and its connection not run out. First Pages: Tiệm Đọc Comment and Tôi Đọc
   Threads Để Bạn Không Phải Đọc.
3. **Same pattern as Instagram auto** (`jobs.queue_youtube_auto_posts`): only a scheduled Facebook post of the last day
   triggers it; "Đăng ngay" does not; a video with any YouTube post but a cancelled one on that channel is left alone, a
   failed one too, so an error that repeats is not retried every minute.
4. **One job per video**: TikTok, Instagram and YouTube of one video run one after another, so YouTube can come a few
   minutes after Facebook, not exactly one.
5. **A run-out connection is skipped quietly** (the Google app in testing mode expires tokens every 7 days): the Page
   shows its existing "Kênh YouTube mất kết nối" warning. A slot missed that way is not made up after 24 hours; the
   member uploads by hand.

**Rejected:** making the video public or setting `publishAt` (waits for Google's verification); retrying a failed upload
by itself; a second warning for a run-out connection.
