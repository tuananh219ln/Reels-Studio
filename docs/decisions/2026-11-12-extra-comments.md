# 2026-11-12 — "Bình luận thêm": more comments of the Page under each reel; no @ tags

The owner (namtc), 2026-11-12, asked for "bình luận 1, bình luận 2" added line by line, and for @ tags of followers.

- **Up to 5 per video** (`videos.extra_comments`, migration 0079), typed on "Nội dung đăng" under "Bình luận ghim".
  The worker writes them after the first comment (the pinned text and the product links), in order, in the same
  round and under the same rules: only on a post with "Tự bình luận" or after "Bình luận ngay", never under a video
  with "Đã dán link tay".
- **Never twice**: each is kept by place with Facebook's id (`publications.extra_comment_ids`, `extra_comment_texts`),
  edited when its text changes, recorded as soon as Facebook takes it, and looked for first after an attempt whose
  answer may have been lost. One removed from the video is left on Facebook (a member deletes it there).
- **No @ tags**: Facebook's Graph API does not let a Page's app tag people in a comment, so an "@name" stays plain
  text; the field says so.
- Videos only: an article keeps its one comment. A clone or TikTok version starts without them.
