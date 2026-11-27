# 2026-11-27 — A shuffled copy's dish comments follow its scenes

A member reported that "Nhân bản xáo cảnh" moved the scenes but left the detailed comments per dish
(`videos.extra_comments`, saved by "Lưu bình luận chi tiết từng món") in the source's order, so under a copy the
comments named the dishes 1, 2, 3… while the reel showed them in another order; they had been reordering them by hand.

- **The comments move with their scenes** in `shuffle.make_copies` and in "Xáo lại cảnh" (and its "Hoàn tác"), on the
  web and through the MCP tool alike. "Nhân bản y hệt" keeps them as they are (the scenes do not move).
- **Which comment goes with which scene:** `extra_comments` has no link to a scene, only a place. The tool asks for one
  comment per dish in the scenes' order, the closing/CTA scene left out, so comment *i* goes with content scene *i*
  when there are as many comments as content scenes or one fewer (the last scene then has none). Any other count
  ("Bình luận thêm" written by hand, not per dish) cannot be matched: the comments keep their order and the copy's
  warnings say so, rather than guessing.
- **Numbers:** when the scenes' list numbers are rewritten (`renumber`), a comment's leading list number ("1. Tên món")
  is rewritten to its scene's new place the same way; with `renumber` off it is kept, like the scene's text.
- No new column (a scene id per comment) for now: the place rule covers how the comments are written today.
