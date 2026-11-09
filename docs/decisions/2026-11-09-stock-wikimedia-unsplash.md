# 2026-11-09 — Wikimedia Commons and Unsplash join the stock sources; each topic group orders them; credit is warned

Brief [docs/specs/them-nguon-anh-stock](../specs/them-nguon-anh-stock/brief.md), with the owner's (namtc) answers on its
review the same day ("Chốt sau review" in the brief). Production of videos 60 and 61 showed Vietnamese dishes with their
own names (canh chua, canh nấm…) missing from Pexels, Pixabay and Openverse.

- **Two more sources, everywhere a stock photo is looked for**: the picker, "Tìm ảnh", "Tự tìm ảnh" and the MCP tools
  `search_stock_photos` / `use_stock_photo` (`source` takes `unsplash` and `wikimedia`). Wikimedia Commons is searched
  in Vietnamese (like Openverse), needs no key and sends a User-Agent naming the app. Unsplash takes an Access Key,
  shared by the team like the other source keys (2026-11-01, Cài đặt › Nguồn tư liệu), on its free plan (50 searches an
  hour for everyone); its download endpoint is called when a photo is used, as its API terms ask, and running out of
  calls says "Hết lượt Unsplash" rather than a bad key. Foodiesfeed stays out (no API).
- **Wikimedia takes every free licence, and the photos that ask for credit are warned.** This reverses, for Wikimedia
  only, the reason of "The picker offers three stock sources; Openverse is public-domain only" (2026-10-31: the
  channel earns money and the app shows no attribution). The owner chose to take CC BY and CC BY-SA photos knowingly:
  the scene keeps the licence, author and page (`scenes.image_credit`, migration 0069), shows "Cần ghi nguồn khi đăng"
  with the line to copy, and the video's pre-render warnings list it (CC BY-SA adds that the video must be shared
  under the same licence). The assistant reads it through MCP and tells the member in chat and on WhatsApp; the app
  sends nothing itself. The app still adds no credit to a post: the member does, from the line. Openverse stays
  public-domain only.
- **Each topic group sets its own order** ("Thứ tự nguồn ảnh" on Kho kiến thức, `knowledge_topics.stock_order`): a
  food group can put Wikimedia first. "Tự tìm ảnh" goes down it, the picker and "Tìm ảnh" start on its first usable
  source, MCP reads it with the groups. A new group, or one reset with "Dùng thứ tự chung", takes the app's order:
  **Pexels → Unsplash → Pixabay → Wikimedia → Openverse**. This replaces the order in "Pexels is the default stock
  library" (2026-11-03: Pexels, Pixabay, Openverse); Pexels stays first in the app's order.
- **A source without its key shows greyed out** in the picker ("chưa cấu hình key") instead of being hidden, for every
  keyed source; a source turned off on Cài đặt is still left out.
