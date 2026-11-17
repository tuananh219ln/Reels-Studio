# 2026-11-17 — YouTube: the app uploads private, the member makes it public

Asked by tuananh219ln, 2026-11-17: "đăng YouTube private và có hẹn lịch, vì không đăng bằng API luôn được". This is the
"connecting their APIs is later work" of [2026-11-08](../decisions.md) for YouTube; Instagram stays posted by hand.

- **Why private only:** Google restricts every `videos.insert` from a Google Cloud project it has not audited (created
  after 28 July 2020) to private viewing, and several sources say `status.publishAt` does nothing then. Asked which
  way to go, the member chose to **upload private now and keep the planned time as a reminder**, not to send
  `publishAt` and not to wait for the upload until the time. The app never sends `publishAt` or `public`; the member
  makes the Short public, or schedules it, in YouTube Studio. If the project is not audited, YouTube may lock the
  upload as private and Studio may refuse to make it public too; the only way out is Google's audit (outside the app).
- **Connection:** "Kết nối YouTube" on Quản lý kênh, Google's OAuth with `youtube.upload` and `youtube.readonly`,
  `access_type=offline`, `prompt=consent`. One connection per YouTube channel, owned by the member who made it
  (`youtube_connections`, migration 0097), on that channel's `channels` row (the one added from its link when there
  is one, else a new row). Tokens are encrypted like a Page token and never sent to the web. Google keeps the refresh
  token across refreshes; a refused refresh (`invalid_grant`) marks the connection "Cần kết nối lại". A Google Cloud
  OAuth client still in "Testing" gives refresh tokens that end after 7 days.
- **Upload:** "Tải lên YouTube" on a video's YouTube tab: a connected channel of the member's own (the Page's channel
  is picked first, as for TikTok, then their only one), a title (100 characters; the video's title by default) and
  "Dự định công khai lúc" (the video's Facebook time still ahead, else the next 07:00, 11:00 or 18:00, Vietnam time).
  It makes a `Publication` (platform `youtube`, `pending`) and a `youtube_publish` job; the worker sends the MP4
  through YouTube's resumable upload, `privacyStatus: private`, `selfDeclaredMadeForKids: false` and
  `containsSyntheticMedia: true` (every video of the app is made with AI, as TikTok's AIGC label), the video's caption
  and hashtags as its description. The session's URL is saved before the file is sent, so "Thử lại" asks YouTube how
  much arrived and goes on, and never makes a second video. The same MP4 goes to one channel once.
- **After the upload:** the post's status is `private` and `scheduled_at` holds the planned time (a reminder only).
  The YouTube tab says "Đã tải lên riêng tư · nhớ công khai lúc …" with "Mở YouTube Studio ↗"; "Bài đăng" shows it as
  scheduled. The worker's YouTube readings (with `YOUTUBE_API_KEY`) look at it hourly from the planned time, for 14
  days at most: the public Data API only answers for a public video, so once it answers the post becomes `published`
  with YouTube's time and is followed like any Short. A private post is never marked removed.
- **A Page's YouTube channel:** `fanpages.youtube_channel_id`, set by the Page's owner among the channels they
  connected, next to the TikTok account; only a default for the upload card. Nothing is uploaded by itself at the
  Facebook slot (unlike TikTok drafts): a private Short no one sees is not worth an automatic upload yet.
- **Rejected:** sending `publishAt` (does nothing for an unaudited project, and would promise a time YouTube may not
  keep); having the worker upload at the planned time (the member chose to upload at once); one connection per member
  instead of per channel (a member may run several channels).
