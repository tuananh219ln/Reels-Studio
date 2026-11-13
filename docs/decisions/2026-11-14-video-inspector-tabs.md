# 2026-11-14 — The video page's side tabs: Logo first, groups that close, "Sẵn sàng đăng?" on top

Asked by tuananh219ln from a spec ("Đặc tả tối ưu giao diện trang Video – Reels Studio", 14/11/2026, measured on video
#90: Thiết lập 2,655 px tall, Đăng bài 2,133 px). The spec is built in three PRs, on the owner's call: this one (the
two tabs), then the fixed header with the render bar's contents and the narrow-screen drawer, then the scene cards.

- **It reverses "the setup tab's section buttons are 'Đi tới:' links"** of
  [2026-11-10 — screen review](2026-11-10-screen-review.md) (owner's choice): with every group but Logo closed and
  showing its values in one line, the jump links have nothing left to jump past, so they are gone.
- **Thiết lập:** "Logo" moves from last to first and stays open, with a small 9:16 frame showing the badge where the
  render lays it. "Âm thanh" is open the first time; "Nhạc nền", "Hình ảnh" and "Chữ & phụ đề" start closed. Which
  are open is remembered per member in the browser (`localStorage`, read and written in try/catch): a convenience,
  not shared state. Closed panels stay mounted, so a file input or a field being typed in keeps working.
- **Reading speed stays a slider** (0,70× to 1,30× in 0,05 steps), shown in a row with its value beside it. The
  spec's "segmented + value" would have dropped the in-between speeds members already use.
- **Đăng bài:** "Sẵn sàng đăng?" (QC tiles, "Tải MP4" beside "Đăng bài", the MP4 player) comes first; Caption and
  Hashtag next; then Bình luận, Sản phẩm Shopee, Gợi ý nhạc and Rà soát an toàn của AI start closed with a summary.
  The three "Copy" buttons that sat under the fields move into their blocks' titles.
- **A red QC check asks before posting** ("MP4 chưa đạt kiểm tra chất lượng", "Vẫn đăng"): still advice, as before,
  never a block.
- `AudioSettings`, `MotionSettings` and `TextSettings` take `bare` for the panels; Cài đặt › Thiết lập mặc định and a
  topic group's "Chữ & phụ đề" keep their cards as they were.

No api, data or render change.
