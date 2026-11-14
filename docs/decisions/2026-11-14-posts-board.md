# 2026-11-14 — "Bài đăng" becomes a board of videos × platforms; TikTok and YouTube posts are recorded by link (part 1)

Asked by tuananh219ln from a spec ("Đặc tả: Trang Bài đăng đa nền tảng & cập nhật view", requester Looper, four
parts P1–P4). Four points conflicted with logged decisions or were too large for one PR; they were put to tuananh219ln,
who chose each time the option noted below. This PR is **part 1**.

- **Scope: P1 only.** The board, its tabs and filters, "Tải MP4" → "Chờ dán link", pasting links with video matching,
  YouTube and TikTok channels on "Quản lý kênh", the new columns and the snapshot table. Part 2 (the readings'
  schedule, the 1h/24h/48h/7d/30d marks, YouTube views by API key, removed-post detection), part 3 (the Meta Suite
  import and "Chưa khớp", "Video ngoài", trending posts read every 15 minutes) and part 4 (TikTok views through
  `video.list`, "Nhập view") come in their own PRs.
- **TikTok through the API stays** (chosen over the spec's "TikTok only by hand"): the posting of
  [2026-11-07](../decisions.md) and [2026-11-13-tiktok-auto-post](2026-11-13-tiktok-auto-post.md) is unchanged; a post
  it made shows "API" on the board, a post made by hand is pasted in ("Link tay").
- **The weekly KPIs, "Sẵn sàng đăng" and "Nhân bản" leave the page, their api stays** (chosen over keeping them). This
  reverses, for the page only, the KPI strip and suggestion cards of 2026-11-03/2026-11-06 ([decisions.md](../decisions.md)):
  `GET /api/posts/kpis`, the medians and the 48-hour mark are unchanged. The "Chưa đăng" tab replaces "Sẵn sàng đăng";
  "Nhân bản" and "Nhân bản y hệt" are in each row's "⋮" menu.
- **The spec's schedule of readings is the plan** (chosen over the daily readings of 2026-11-03), for part 2: hourly in
  the first 48 hours, marks with a tolerance and interpolation, followed for 90 days. Part 1 only lays the ground: every
  Facebook reading also adds a `post_metric_snapshots` row and the `post_metrics` rows were copied in; the daily
  schedule and the `48h` mark are unchanged until part 2 lands.
- **Mapped onto the tables there are, as the spec allows:** no `posts` table, `publications` gets `source`,
  `external_id` (unique per platform), `channel_id`, `mp4_downloaded_at`, `published_at_source` and the status
  `pending_link`; the spec's `publishing` is `pending`, `removed` is `deleted`. No `channels` row for a Facebook Page
  (`fanpages`) or a TikTok account (`affiliate_accounts`, so "Kết nối TikTok" and a Page's TikTok account keep working):
  `channels` holds YouTube channels only. "Thêm kênh" from a TikTok link makes a TikTok account owned by its adder.
- **Facebook links are recorded on the member's own Pages only**, as only a Page's owner posts to it
  ([2026-11-09-page-owner-posts](2026-11-09-page-owner-posts.md)). Their numbers come from the worker at once; Facebook
  is never called in a request (2026-11-03). TikTok and YouTube links are read with oEmbed in the request (no key, 8 s):
  a member waits for the preview, and it is not long work like a script or a render.
- **Matching** follows the spec's §4.4; the length part is always left out for now, as oEmbed gives none (the
  YouTube Data API in part 2 will). A link of a channel not added is refused ("Kênh chưa khai báo").
- **Times are Vietnam time** (`Asia/Ho_Chi_Minh`, the repo's rule; the spec's `Asia/Bangkok` is the same UTC+7).
- **"Quản lý Page" is renamed "Quản lý kênh"** everywhere it is shown.

Rejected: a `posts` and a `channels` table for every platform (two homes for a Page and a TikTok account, and every
existing reading, check and comment to move); reading Facebook links' Page through Graph in the request (against
2026-11-03).
