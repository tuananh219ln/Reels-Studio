# 2026-11-18 — Affiliate shows which posts' comments still lack a link

Asked by the owner (namtc) on the "Video đã đăng" screen: "kiểm tra xem video nào đã có bình luận gắn link, để đỡ
phải bấm vào từng cái", and the comments and products in "Bình luận và bài đăng" to add links by hand. Mockups of the
list and the drawer approved in the session ("ok làm hết đi").

- **What counts as a link:** a Shopee address (`shopee.vn`, `s.shopee.vn`, `shp.ee`, `shope.ee`, with or without
  `https://`) in any of the Page's comments under the reel. Not whether it is the right product or the member's own
  commission: that stays the products column's job.
- **Two sources, no new Facebook call.** The texts the app wrote (`comment_text`, `extra_comment_texts`), and the
  Page's own comments the worker already received when reading visitors' comments (it dropped them before); only
  `link` / `no_link` / `none` is kept (`publications.own_comment`, migration 0107), not their text. So a link pasted
  by hand is seen within about 30 minutes, but only for reels of the last 14 days (the reading's window); older ones
  pasted by hand show "Chưa rõ".
- **"Thiếu link" is a tab of its own** beside the attach tabs, since it cuts across them: a video counts when one of
  its Facebook posts is `missing`, `updating` or `none`. "Chưa rõ" is not counted, so the tab never lists a video
  only because nothing was read.
- **"App đã bình luận" is gone** from the comment column: in green it read as done while the comment held no link.
  The column shows the link state, one button ("Thêm link" / "Xem bình luận") and ⋯ for "Sao chép" and "Đã dán link
  tay", which moved there as the less used actions.
- **The drawer reuses the video page's blocks** (`EngageContent`, products first) instead of a copy, so pasting links,
  Shopee suggestions and the pinned comment behave as on the video page.
