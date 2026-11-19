# 2026-11-19 — Instagram through its Page, and all four platforms in "Đăng lên N nền tảng"

Asked by tuananh219ln, 2026-11-19 ([brief](../specs/instagram-posting/brief.md)): the team's Instagram accounts are
Business accounts linked to their Facebook Pages, and the token pasted for a Page now has `instagram_basic` and
`instagram_content_publish`. This is the "connecting their APIs is later work" of [2026-11-08](../decisions.md) for
Instagram, and it reverses two points of [2026-11-14 publish panel](2026-11-14-publish-panel.md) and
[2026-11-14 video editor spec](2026-11-14-video-editor-spec.md), at the member's request.

- **Instagram goes through its Page**, with the Page's own token the app already keeps: no connection or OAuth of its
  own. The Page check reads the linked account (`fanpages.instagram_user_id`, `instagram_username`, migration 0111);
  "Quản lý kênh" shows it. Only the Page's owner posts to its Instagram (as for Facebook, 2026-11-09).
- **Public at once.** Instagram's API has no draft; "Đăng ngay" publishes the Reel. The same MP4 goes to one Instagram
  account once.
- **"Hẹn giờ" works for Instagram as for Facebook.** Instagram's API has no scheduled time either, so the post waits
  in the app (`scheduled`) and the worker's minute round starts it at its time; "Hủy hẹn" takes it back before then.
  A post the worker reaches more than 24 hours late is cancelled, with a failed job saying why, instead of going out
  by itself (the member's choice).
- **Every platform row is a checkbox.** Reverses "YouTube Shorts and Instagram stay as before, posted by hand: their
  rows say 'Đăng tay', have no checkbox" (publish panel) and "'Hẹn giờ' turns its [TikTok] tile off" (video editor
  spec). With "Hẹn giờ", TikTok (a draft) and YouTube (a private upload, titled with the video's title, the time kept as
  its reminder) still go at once, and each shows done ("✓") once through: the member knows a TikTok post is a draft and
  a YouTube one private, so the card does not say so again.
- **"Đã đăng tay" stays** in "Tùy chọn khác" for Instagram and YouTube.
- **Not in this round** (the member's choice): Instagram's numbers and comments (need `instagram_manage_insights` and
  `instagram_manage_comments`), Trial Reels, collaborators, photos and carousels, and Instagram in a Page's queue.
- **Rejected:** a separate Instagram login per member (the Page already carries the account and its token); posting a
  late Instagram post anyway after the worker was down (it could put out old videos unseen).
