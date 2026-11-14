# 2026-11-14 — The video page's side panel: "Bình luận & Sản phẩm" is a tab of its own

Asked by tuananh219ln from a spec ("Đặc tả: Tách “Bình luận & Sản phẩm” thành tab riêng trong side panel"): the
"Đăng bài" tab had grown too long.

- **It changes [the video editor spec](2026-11-14-video-editor-spec.md)**, which kept the comments and the products
  as blocks of "Đăng bài" between the caption and the hashtags. The panel now has three tabs: "Đăng bài" (the status
  card, "Nội dung đăng", "Hashtag"), "Bình luận & Sản phẩm" (key `engage`: "Bình luận", "Sản phẩm Shopee", moved
  unchanged) and "Thiết lập". "Đăng bài" stays the tab the page opens on; the tab is not kept in the URL.
- **An orange dot** (antd `Badge dot`) sits on "Bình luận & Sản phẩm" while the video has no product attached, as the
  progress line's "Affiliate · Chưa gắn sản phẩm" does.
- **The progress line's "Affiliate"** opens that tab and scrolls to "Sản phẩm Shopee"; on a narrow screen the drawer
  opens on it.
- Every tab stays mounted while hidden (`forceRender`), so a field being typed in keeps its text across a tab change
  and is saved when it loses focus, as before. The spec's optional short label ("BL & Sản phẩm") is not built: antd's
  "…" takes over when the panel is too narrow.

No api, data or render change.
