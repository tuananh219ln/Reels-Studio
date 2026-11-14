# 2026-11-14 — The video page: 60/40 with two side tabs, a 182 × 324 frame with its tools beside it, posting by platform

Asked by tuananh219ln from a spec ("Đặc tả giao diện trang chỉnh sửa video – Reels Studio", @Looper, 14/11/2026,
approved on a live preview of the page). The spec was written on the page before
[the bento layout](2026-11-14-video-bento-layout.md); asked in the same session, the owner chose to follow the spec.

- **It reverses [the bento layout](2026-11-14-video-bento-layout.md)** (owner's choice): the side panel has two tabs
  again, "Đăng bài" and "Thiết lập" (no Thiết lập drawer), the tab row stuck at the panel's top while it scrolls.
  The post's texts are blocks in a fixed order, not tabs: the status card, "Nội dung đăng" (Caption, with "Copy caption
  + hashtag"), "Bình luận", "Sản phẩm Shopee", "Hashtag" last. The scenes no longer scroll in a tile of their own from
  1400 px; they scroll with the page.
- **It reverses [the half-and-half split](2026-11-14-video-side-panel-half.md)**: from 1100 px the scenes take 60% and
  the panel 40% (`minmax(0,3fr) minmax(0,2fr)`). Below 1100 px the panel stays a drawer, now "Đăng bài / Thiết lập";
  the spec's "one column under 1200 px" was only a proposal and was not taken.
- **It reverses the frame of [the scene cards change](2026-11-14-scene-cards-one-open.md)**: the frame is 182 × 324
  (was 150 px wide with every tool laid over it on hover). Only Xem / Cắt / Sửa / Di chuyển (and "Xoá video" for a
  clip) stay inside it, 40 px icons down its right edge, shown on hover, tap or keyboard focus (they stay clickable
  while faded, as the old overlay's buttons were). The ways to put a picture in are a column of their own beside the
  frame, always shown while editing, in three groups (Lấy ảnh, Tìm ảnh, Tạo mới); short labels on screen ("Pexels",
  "Dán link", "Google", "TikTok") with the full names kept as `aria-label`. The studio keeps its layout.
- **"Tự chọn, kiểm tra lại" and "Giữ ảnh này" are gone from the card** (owner's choice, "bỏ hẳn như đặc tả"), which
  drops the review mark of "2026-11-02 — Tự tìm ảnh" and of the Google Ảnh photos (2026-11-08), both in
  [decisions.md](../decisions.md). The api still sets `image_auto` and accepts `image_checked`; only the web stopped
  showing them, and the messages that pointed at the mark now say to look at each scene's photo.
- **"Gợi ý nhạc" and "Rà soát an toàn của AI" are no longer shown** (spec). The data stays in the api and the MCP tools.
  A hand-written video's warning that the AI did not review it stays, in "Nội dung đăng": it is a safety reminder,
  not the review. The spec's open question (the AI's rewritten sentences as an ⓘ beside Caption) is not built.
- **Logo** is two rows with no preview frame.
- **Posting from the status card:** a 2×2 grid of platforms and "Đăng lên N nền tảng". Only Facebook and TikTok are
  posted by the app (owner's choice: YouTube Shorts and Instagram have no API here, so their tiles open "Tùy chọn khác"
  on their tab to record a post made by hand). Facebook goes to the member's Page with the comment written when the
  reel is live; TikTok as a draft to the member's connected account's inbox (direct posting with a privacy level stays
  in "Tùy chọn khác"). TikTok cannot be scheduled, so "Hẹn giờ" turns its tile off.
- **One platform after the other, from the open page:** the api runs one job per video, so the page sends TikTok once
  Facebook's job has ended (seen by its polling). Leaving the page before that leaves TikTok unsent; the card then
  shows only Facebook. No api change was made for this.
- **"Tùy chọn khác"** is the former "Đăng bài" drawer, unchanged (a Page's queue, TikTok direct, "Đã đăng tay").
- **The note after posting** is the page's own fixed element, not antd's `notification`, whose `top` is set per
  instance: its bottom sits 8 px above the side tabs' line, measured when shown. It goes after 7 s when all went out
  and stays while something failed.
- **Per-platform rows** come from `web/src/lib/postResults.ts`; the progress line's "Đăng" step reads the same
  ("X/Y nền tảng · hh:mm", green). A Facebook failure shows its reason and "Thử lại" while it is the video's last
  failed job (the api sends only that one); otherwise the row says "Đang đăng…" until the post settles. Every Facebook
  post, cancelled and deleted ones included, stays under "Lịch sử bài Facebook", folded.
- The MP4's size is read from a one-byte range request of the MP4 (its `Content-Range`); the resolution is the
  render's fixed 1080×1920.

No api, data or render change.
