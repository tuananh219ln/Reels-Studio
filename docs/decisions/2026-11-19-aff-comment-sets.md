# 2026-11-19 — "Bộ bình luận": a Page's ready-made link comments, written after the food comments

From the spec "Đặc tả: Bộ bình luận Affiliate theo Page" (v1.0, 19/11/2026), asked by tuananh219ln ("code đi, có giải
pháp tiện hơn thì đề xuất"). Built: the spec's rounds 1–3 and the per-video off switch and set choice from round 4.

- **No new product table.** The spec's "kho 100 sản phẩm của page" is the Page's group's `affiliate_products`
  (a Page posts one group); they get `short_name`, `category` and `tags`, edited without undoing the approval. Its
  `dead_link` / `hidden` status is the existing "usable" rule (approved, still meeting the rules, the daily check),
  so no second link checker.
- **No `page_aff_settings` or `post_aff_comments` table.** The settings are one JSONB on `fanpages`
  (`aff_settings`), the log is on the post as the "Bình luận thêm" are (`aff_set_ids`, `aff_comment_ids`,
  `aff_comment_texts`), so the comment worker writes, edits and recovers lost answers the same way.
- **Links are the pinned comment's** (`affiliate.link_for`): the Page's own Shopee account makes one per video and
  Page, whose sub_ids already name both; a set id is not added (it would need a link per set and the existing orders
  reading cannot read it). Without a Page account, the link saved on the product.
- **Pacing narrows [2026-11-18-comment-pacing](2026-11-18-comment-pacing.md) for set comments only**, as the spec
  asks: the first a random 5–10 minutes after the last food comment, the others 3–7 minutes apart (the Page's
  settings). The post waits with a request dated ahead, so a restart loses nothing, and the Page writes other reels'
  comments meanwhile. Food comments keep 45–75 s; the reel-age stages and 100 comments a Page a day apply to set
  comments too.
- **The choice is kept from the first set comment** (`publications.aff_set_ids`); before that it is recomputed each
  time (preview included), so a video edited before going live gets the sets matching its new scenes. "random" uses
  the video's id as seed so the preview is what goes up.
- **Not built:** "Sửa nội dung cho video này" (turn the video's sets off and write a "Bình luận thêm" instead),
  "Đăng aff ngay, bỏ chờ", automatic retries 1/3/10 minutes (a failed set comment waits for "Bình luận ngay" like a
  food comment, and stops the comments after it), the `hidden_by_fb` check 5 minutes later, CSV import of the new
  columns, "AI gợi ý tên ngắn + nhóm + tags", and the summary line on "Quản lý kênh". Drag and drop is up/down
  buttons. The short names, groups and tags are edited in the "Bộ bình luận" tab, beside the sets that use them,
  not in "Sản phẩm".
- **Suggested next**: fill short names, groups and tags through the member's own assistant over MCP (as the food
  comments are, [2026-11-18-food-comments](2026-11-18-food-comments.md)) rather than an AI call in the app.
