# 2026-11-15 — Articles take up to 10 photos from a scene's tools, stock photos included, with the Page's logo laid on when posted

Round 1 ("Đợt 1 — Logo + nguồn ảnh") of the spec "Đặc tả: Kế hoạch 30 ngày cho Bài viết" (by Looper), asked by
tuananh219ln, who chose on 2026-11-15 between the options below. Rounds 2–4 (scheduled posting with retries, the
articles' 30-day plan, the 3-step "Tạo bài viết" dialog) follow in their own PRs.

- **Stock photos are allowed for articles.** This reverses "an article never takes one" of
  [2026-11-06 — Photo and text posts ("Bài viết") are built, with no stock photos](../decisions.md) at the owner's
  choice: the photos are taken with the same tools as a scene's (upload, paste, "Kho tư liệu", the stock sources in
  the order of the article's group, Google and TikTok searches whose links are pasted back, an AI photo), plus the
  "Thẻ chữ". "The app never searches Google by itself" (2026-11-07) stands: those buttons only open the member's
  browser. A photo from a stock photo site keeps the same watermark warning as on a scene, and a stock licence's credit
  line is kept with the photo.
- **The logo stays on `brands`** rather than the spec's new `brand_kits` table and "Logo chèn ảnh" page (the owner's
  choice): one Page has one brand and one logo (2026-11-13), managed on its card in Quản lý kênh, which now opens "Logo
  trên ảnh bài viết" (place on a 3×3 grid, width, margin, opacity, a white logo for dark photos and its brightness
  threshold, samples in 1:1, 4:5 and 1.91:1). Videos keep their round badge; a photo gets the uploaded logo itself.
  SVG is not taken (Pillow cannot draw it), as for the video logo.
- **The logo is laid on when posting, for the Page posted to**, instead of the spec's `render_logo` job writing a
  `rendered_url` when the article is saved: an article has no Page until "Đăng" chooses one, and a stored copy would go
  stale whenever the logo or a setting changes. The stored photo never changes; the preview (`.../preview?fanpage_id=`)
  is drawn by the same code as the posted copy, so what is shown is what is posted. Each photo has its own switch and
  place.
- **Several photos go as one post**: each uploaded unpublished (`temporary` when scheduled) and attached to one feed
  post, with "never posted twice" unchanged (the text is stamped before the feed post; a lost answer is looked for).
  One photo still goes through `/photos` as before.
- **One AI photo per press**, not the spec's four: a scene's "Tạo ảnh AI" makes one, and four would cost four times as
  many of Cloudflare's free daily photos (or Gemini's paid ones) for every press. It uses the team's provider and its
  daily limit and messages, the same as scenes.
- Photos an article already had move into `article_images` with their logo off, so a draft looks as it did.
