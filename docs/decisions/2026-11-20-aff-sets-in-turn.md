# 2026-11-20 — "Bộ bình luận": free sets take turns by video, not by last use

Narrows [2026-11-19-aff-comment-sets](2026-11-19-aff-comment-sets.md), asked by tuananh219ln: every video not posted
yet showed the same sets (3 and 4) under "Bình luận aff tự động", since the rotation read only when a set last went
up, and nothing had gone up between them ("chưa đăng mà cũng nên sửa xem trước cho chuẩn").

- **Sets free to use** (enabled, enough usable products, not used on the Page within `no_repeat_days`) are one cycle,
  higher priority then the older set first, and each video starts it at its own place (its id times
  `sets_per_post`): videos made one after another show and get different sets. The same video always gets the same
  answer, so the preview is what goes up while nothing else goes up in between.
- **Among them, how long ago a set was used no longer counts**; sets used within `no_repeat_days` still come back only
  when too few are free, the longest unused first.
- **Sets matching the video equally well take turns the same way** (it was the older set every time).
