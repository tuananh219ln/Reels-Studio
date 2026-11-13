# 2026-11-14 — Scene cards: one open at a time, a 150 px frame with its tools over it, one toolbar row

The third of three PRs for "Đặc tả tối ưu giao diện trang Video – Reels Studio" (asked by tuananh219ln; before it,
[the side tabs](2026-11-14-video-inspector-tabs.md) and [the fixed header](2026-11-14-video-page-header.md)).

- **It reverses the 220 px left column** of [2026-11-12 — scene card layout](2026-11-12-scene-card-inset-layout.md)
  (owner's choice in the same session, "theo đặc tả"): the frame is 150 px on every card, a "Video xuyên suốt" one
  included, so every card's frame is still the same size. The picture's tools leave the column under the frame and
  lie over it on hover (always on a touch screen, and while there is no picture): its own tools as a row of small
  icon buttons on top, keeping their names as `aria-label` and tooltip, then the ways to put a picture in. The overlay
  lets clicks through between its buttons. The studio's "Chỉnh cảnh N" keeps them under its picture, as before.
- **One card open at a time:** opening a card closes the one open; "Mở tất cả" still opens every card, on purpose.
  When the page opens, the first scene with a red reason is open, else a draft's first scene, else none (a draft had
  every card open before; a rendered video only those with a red reason). "Còn N lỗi cần sửa" opens the first such
  scene alone. "Thêm cảnh" opens the new one.
- **Keys:** ↑/↓ only on a scene's title row (in a text field they still move the caret); Ctrl/⌘+Enter anywhere in a
  card saves the field (by leaving it) and opens the next scene.
- **A clip scene's frame has "Ảnh | Clip"**, starting on "Clip"; both stay in the page, the one not shown hidden, so
  the drawn preview is still current when switched to. The clip has no controls in the frame (they would sit under
  the tools); it plays muted while pointed at, and "Xem" and "Cắt video" play it with controls.
- **The title options and the video's kind are one toolbar row**; the options open from a button showing the title
  in use, drawn while closed so "Kịch bản viết bởi …" stays in the page.
- **The spec's "warning with its fix button" (e.g. "Lặp clip") is not built:** the api's warnings are plain text with
  no action attached; they are one line each instead. Drag-to-reorder (optional in the spec) is not built either.
- Word counts move to the field's label row, everywhere `AutoSaveField` counts words (the studio too).

No api, data or render change.
