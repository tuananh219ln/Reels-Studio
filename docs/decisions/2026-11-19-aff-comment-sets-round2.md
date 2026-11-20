# 2026-11-19 — "Bộ bình luận", round 2: retries, "Đăng aff ngay", the Page's line, file columns

Follows [2026-11-19-aff-comment-sets](2026-11-19-aff-comment-sets.md), asked by tuananh219ln ("Oke làm đi") after PR
#303. Builds four of its "Not built" items; the rest stay for later.

- **Automatic retries, set comments only.** A set comment Facebook refuses is tried again after 1, 3 and 10 minutes
  (a request dated ahead, as the Page's rests are), counted in `publications.aff_retries`; after three it waits for
  "Bình luận ngay" as before. The pinned and "Bình luận thêm" comments keep failing once, as decided for comments
  generally ("a failed comment never loops"): only set comments got the spec's retries.
- **"Đăng aff ngay, bỏ chờ" skips the post's own wait, not the Page's limits.** The post's next comment is asked for
  the worker's next round; the Page's minute between videos, its 100 a day and an older reel's day hours still hold.
  It also gives a failed set comment its retries back.
- **"Quản lý kênh" shows one line per Page** (sets usable of all, sets a reel, or off), linking to the Page's sets;
  no count of comments written, which would need a log the app does not keep.
- **The file's new columns are optional and never clear.** "Tên ngắn", "Nhóm", "Tags" are read when present; an
  empty cell keeps what a member set on the tab, so Shopee's own file imports as before.
- **Still not built:** "Sửa nội dung cho video này" (turn the sets off and write a "Bình luận thêm"), the
  `hidden_by_fb` check (one more Facebook call per comment; wait to see whether hiding happens), AI labels (through
  the member's assistant over MCP when built).
