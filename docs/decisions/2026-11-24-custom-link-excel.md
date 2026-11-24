# 2026-11-24 — Shopee Custom Link by Excel (option A: the tool writes the file, a member uploads it once)

Asked by the owner. The Shopee Affiliate account has no Open API yet (AppID `--`), so `shopee.short_link`
(`generateShortLink`) cannot turn a product page into an affiliate link. Shopee's own "Custom Link" page does it
from an Excel file (up to 10,000 links; header `Liên kết gốc, Sub_id1 … Sub_id5`).

- **Export** `GET /api/affiliate-products/custom-link/export.xlsx` (`routes_custom_link.py`): the open group's approved
  products I added that have a `page_url`; by default only those with no `url` yet ("Gồm cả món đã có link" adds the
  rest). A teammate's products are left out: their link is theirs and the import never overwrites it.
- **Built from Shopee's own template.** A workbook made from scratch was refused ("Đăng tải thất bại, vui lòng sử dụng bản mẫu có sẵn"); the same rows in a copy of the template were taken. The template ships as `api/src/reels_api/custom_link_template.xlsx` and rows are appended to it (sheet "Sheet1" and its document properties stay).
- **`Sub_id1 = p{fanpage_id}`**, the exact form `affiliate_rounds.read_orders` reads (`^([vp])(\d+)$`); Sub_id2–5 empty.
- **Trade-off, accepted:** the sub id is fixed when Shopee converts the link, so an order is measured to the **Page**,
  never to the video. A per-video file would mean exporting again for every scheduled video; not built.
- **One Page per file.** A product has one `url`, shared by every Page of its group, so the sub id can name only one
  Page. A group with one active Page uses it; with two or more the export asks which one (`fanpage_id`; the modal has
  a Page select and a warning that the orders of the others are not measured to them), and a Page that does not post the
  group is refused (2026-11-25, the owner's choice; it was a refusal before). A group with no active Page refuses.
  A link per (product, Page) would measure each Page; it is a separate piece of work (new table, `link_for` and
  `commission_to` change).
- **Assumption:** the Page has no Shopee account with credentials. When it has one, `affiliate.link_for` makes its own
  link per video and ignores the saved `url` (`commission_to` "page_account").
- **Limit:** 10,000 links per file, checked in code (one file is enough for the current ~200 products).
- Not done: no call to Shopee (no API), no upload or download from Shopee, no per-video sub id, and the CSV import
  "Lấy link hàng loạt" (`IMPORT_COLUMNS`, `/import`) is untouched.

## Import (`POST /custom-link/import/preview` and `/import`, multipart: `knowledge_topic_id` + `file`)

- Two steps like the CSV import: the preview writes nothing, the import writes. Limits: 5 MB, 10,000 rows.
- Matching is by the **original link normalised** (`routes_custom_link.page_key`: the shop and item from the address,
  so a tracking tail or a slug does not matter) against `page_url`, **only among the products in the chosen group**.
  Only products **I added** get the link; a page only a teammate's product has is listed as `others` and keeps its
  link (never overwritten). This is not `_sorted_rows`: the CSV import's `copy` state (my own row beside a
  teammate's) does not apply, nothing is created here.
- An approved product stays approved unless `affiliate.problems` now fails it (as the CSV import); comments already
  under live posts are asked to follow the new link (`ask_comment_refresh`, forgetting Page-account links).
- **Shopee's real result file** (seen 25/11/2026 with three links): a **CSV** (UTF-8 with BOM), the template's six
  columns, then `Liên kết chuyển đổi` and `Lí do thất bại`; a converted link was a new `s.shopee.vn/...` even when the
  original was already a short link. The import reads CSV or `.xlsx` (by the file's first bytes), takes the columns by
  those names, and shows Shopee's own failure reason on a failed row. A file without `Liên kết gốc` is refused,
  naming the columns it has. Failed rows of a real bigger file (what Shopee says for a bad link) are still unseen.
