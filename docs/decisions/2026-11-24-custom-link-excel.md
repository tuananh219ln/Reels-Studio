# 2026-11-24 — Shopee Custom Link by Excel (option A: the tool writes the file, a member uploads it once)

Asked by the owner. The Shopee Affiliate account has no Open API yet (AppID `--`), so `shopee.short_link`
(`generateShortLink`) cannot turn a product page into an affiliate link. Shopee's own "Custom Link" page does it
from an Excel file (up to 10,000 links; header `Liên kết gốc, Sub_id1 … Sub_id5`).

- **Export** `GET /api/affiliate-products/custom-link/export.xlsx` (`routes_custom_link.py`): the open group's approved
  products I added that have a `page_url`; by default only those with no `url` yet ("Gồm cả món đã có link" adds the
  rest). A teammate's products are left out: their link is theirs and the import never overwrites it.
- **`Sub_id1 = p{fanpage_id}`**, the exact form `affiliate_rounds.read_orders` reads (`^([vp])(\d+)$`); Sub_id2–5 empty.
- **Trade-off, accepted:** the sub id is fixed when Shopee converts the link, so an order is measured to the **Page**,
  never to the video. A per-video file would mean exporting again for every scheduled video; not built.
- **One Page per group (option C).** A product has one `url`, shared by every Page of its group, so the sub id can
  name only one Page. Each group has one Page today. A group with no active Page, or with two or more, refuses the
  export (saying why) instead of measuring orders to the wrong Page. A link per (product, Page) would lift this; it
  is a separate piece of work (new table, `link_for` and `commission_to` change).
- **Assumption:** the Page has no Shopee account with credentials. When it has one, `affiliate.link_for` makes its own
  link per video and ignores the saved `url` (`commission_to` "page_account").
- **Limit:** 10,000 links per file, checked in code (one file is enough for the current ~200 products).
- Not done: no call to Shopee (no API), no upload or download from Shopee, no per-video sub id, and the CSV import
  "Lấy link hàng loạt" (`IMPORT_COLUMNS`, `/import`) is untouched.
