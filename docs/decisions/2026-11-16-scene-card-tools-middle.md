# 2026-11-16 — "Video xuyên suốt" scene card in three columns; no drag to reorder scenes

Asked by namtc, from a sketch agreed in the session.

- **Three columns from 576 px:** the 150 px preview, a 170 px middle column with "Chỉnh vị trí chữ & ảnh chèn", the
  scene's picture tools and the "Ảnh chèn" block, then the fields. Before, the button, tools and block sat in rows
  under the preview, leaving a tall empty strip beside them; now the card is shorter and the picture's tools sit next
  to the picture. Narrower than 576 px it is one column, as before. A slide video's card is unchanged.
- **Reverses [2026-11-14 — scene drag reorder](2026-11-14-scene-drag-reorder.md)** (owner's choice in the session):
  the ⋮⋮ handle and the drop on a card are gone. "Lên trên" / "Xuống dưới" are the one way to reorder, saved through
  the same `PUT /videos/{id}/scene-order`.

No api, data or render change.
