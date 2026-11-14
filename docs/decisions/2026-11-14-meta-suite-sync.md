# 2026-11-14 — Reels posted outside the app are imported from each Page and matched to videos ("Bài đăng" part 3)

Part 3 of the spec of [2026-11-14-posts-board](2026-11-14-posts-board.md) (§1.7, §4.3, §4.4), asked by tuananh219ln.

- **The worker imports, a request never calls Facebook** (2026-11-03): between jobs, each Page in use with
  "Đồng bộ bài ngoài app" on (the default, its owner's switch on "Quản lý kênh") is imported hourly, and any Page when
  "Đồng bộ ngay" asked. Reels and videos since the last import less 2 hours, 30 days back the first time; only
  published ones (a reel scheduled in Meta Business Suite comes once it is out).
- **A reel the app has is skipped**: by its id (`external_id`) or the app's own reel id (`remote_id`), so a reel posted
  by the app is never imported again, and an import never doubles.
- **Recorded under the Page's owner** (`created_by_id`; the member who connected it when it has none, else not
  imported): a post needs a maker, and posting on a Page is its owner's (2026-11-09).
- **Read at once, matched or not** (§4.3 step 5): the readings of part 2 apply to it like any reel.
- **Matching** is the pasted links' (§4.4), with the reel's length from Graph: confirmed at 85 % and 10 points ahead,
  else suggested from 50 %, else unmatched. "Chưa khớp" lists both kinds: "Xác nhận", "Chọn video khác", "Video
  ngoài", "Bỏ qua"; "Xác nhận tất cả gợi ý" for the rows ticked.
- **A post may now have no video and no article**, only as `meta_suite` or `manual_link` (migration 0089 widens the
  `one_target` check). "Video ngoài" is a row of its own on the board; a link pasted may be one too. The comment
  readings, the Page's dashboard, the KPIs and medians keep to posts with a video or an article, as before.
- **"Bỏ qua" stops the readings** (`match_status = ignored`). A matched imported reel offers "Đổi video khớp" and "Bỏ
  khớp", not the app's "Xóa", which would take the reel down on Facebook; "Gỡ" on an imported reel only takes it out of
  the app, by its Page's owner.
- **Not done:** a video deleted from the app still takes its posts with it (the spec's "keep them as Video ngoài", §7):
  `publications.video_id` is `ON DELETE CASCADE` and video deletion already weighs a teammate's posts; changing it is
  its own decision. TikTok views (part 4) are next.
