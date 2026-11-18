# 2026-11-18 — A product change edits the comments already written under live posts

Asked by tuananh219ln ("cập nhật link sản phẩm aff có trong bài viết"). Before, only changing a video's or article's
product list asked the worker to edit its live posts' comments; editing a product's link, unapproving, deleting it or
the daily check dropping it left the old link on Facebook.

- Any such change calls `affiliate.ask_comment_refresh`, which sets `comment_requested_at` on each live Facebook post
  that already has a comment and whose video or article carries the product. The existing worker round then edits the
  comment (no new comment, no new Facebook call type).
- A video marked "Đã dán link tay" is skipped; a post with no comment yet writes the current text when its turn comes.
- A changed link or product page drops the product's `affiliate_links` so the Page's own short links are made again.
- Not covered: the Reel's caption (Facebook's API here cannot edit it), which never holds links anyway.
