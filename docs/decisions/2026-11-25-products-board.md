# 2026-11-25 — Affiliate › Sản phẩm has a board of the four steps beside the table (the table is the default)

Asked by the owner after the table and its group column were found crowded ("cần sự đột phá").

- **The screen follows the work.** A product goes: drafts short on stars or sales → drafts to approve → approved Shopee
  products with no affiliate link → ready (approved, with a link or not a Shopee one). Each step is a column of the
  board with its count, so the stage tabs and the "chưa có link" figure are not needed beside it.
- **Custom Link sits in the column that needs it** ("3 · Cần link": "Xuất file Custom Link", "Nhập kết quả Shopee"),
  see [2026-11-24-custom-link-excel](2026-11-24-custom-link-excel.md).
- **The group column on the left is gone**; the group is a select on top (it cost 240–480 px a row and its Page
  names stretched it). Every group, the count and its Pages are in the select's options.
- **The table stays the default** ("Bảng", the owner's choice after trying the board) for ranking by commission, ticking
  rows and deleting or approving many: the same filters, actions and selection as before. "Quy trình" is one click
  away; the choice is kept in the browser (a per-viewer convenience).
- No api change; the four steps are derived from fields the list already returns (`status`, `short_on_counts`,
  `url`, `platform`).
