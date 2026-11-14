# 2026-11-14 — TikTok views through `video.list` once TikTok approves it, and "Nhập view" until then ("Bài đăng" part 4)

Part 4 of the spec of [2026-11-14-posts-board](2026-11-14-posts-board.md) (§3.4), asked by tuananh219ln.

- **The scope waits for TikTok's approval.** The developer app is approved for `user.info.basic`, `video.upload` and
  `video.publish` only ([2026-11-07](../decisions.md), `tiktok.SCOPES`); asking TikTok for a scope it has not approved
  makes every "Kết nối TikTok" fail. So `video.list` is asked for only with `TIKTOK_VIDEO_LIST=1`, set once TikTok has
  approved it; accounts connected before then connect again to grant it.
- **Read only where granted**: a TikTok post is read when its account's connection holds `video.list`
  (`tiktok_connections.reads_views`), through `/v2/video/query/`, 20 ids per call, with the account owner's token, on
  the schedule of [part 2](2026-11-14-post-readings-schedule.md). Its `create_time` replaces the posting time unless the
  member typed one. Missing from two answers an hour apart, it is removed, as a YouTube Short is; a failed connection
  ("Token hết hạn", rate limit, network) reads nothing and is tried an hour later, never marking a post removed.
- **The spec's token refresh job is not added**: `tiktok_connections.access_token` already refreshes a token about to
  end before each use, and saves both new tokens at once.
- **"Nhập view"** for every other TikTok post that is out (any member, as recording a link is): views, and optionally
  likes, comments, shares and when they were read (now by default; never in the future or before the post went live),
  kept as a reading with `raw = {"manual": true}` that settles the marks it passed. No scraping of TikTok's pages.
- **On the board** a TikTok post read through its connection is labelled "OAuth"; one without says "Kết nối TikTok để
  tự cập nhật view" (or "Cần kết nối lại TikTok") in its tooltip. "Quản lý kênh" shows "Đã kết nối, tự cập nhật view",
  "Đã kết nối", "Chưa kết nối" or "Token hết hạn".
- **Not covered**: a TikTok post sent through the API keeps TikTok's `publish_id`, not the video's id, so it is read
  only once its link is recorded (the TikTok card's "Đã đăng tay" link, or pasted on "Bài đăng").
