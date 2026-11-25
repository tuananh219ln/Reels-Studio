# 2026-11-18 — Articles list: no "Làm reel từ bài này", buttons in one row, compact rows

Asked by the owner (tuananh219ln) from a spec ("Tối ưu giao diện trang Bài viết"). The list's rows were about four
to a screen because the action buttons stacked.

- **"Làm reel từ bài này" leaves the list only.** This narrows the 2026-11-06 entry on articles, which put the
  button on the article: the detail page keeps it and the api (`POST /articles/{id}/make-video`) is untouched, as the
  spec said ("UI only").
- **"Đăng bài" and "Xoá" sit in one row** (Xoá keeps its confirmation and stays the maker's alone).
- **Rows are `size="middle"` with 48 px thumbnails**, title on one line, the second line clamped to two.
- **"Số 48h" has three states** ("—", "Chưa đo", the counts) with a header tooltip. The counts use Ant Design icons and
  no "·" between them, following 2026-11-10 (UI rules), not the spec's sample; shares stay in the cell's tooltip.
- The other columns (Lịch đăng, Dạng bài, Nhóm chủ đề, Tạo) stay, so the table still scrolls sideways.
- Not done (spec section 6, optional): "Đăng lại" for a posted article and opening the article by clicking its row.
