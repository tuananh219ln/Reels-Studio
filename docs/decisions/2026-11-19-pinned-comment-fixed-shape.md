# 2026-11-19 — The pinned comment has a fixed shape; only its survey line is typed

Asked by tuananh219ln from a spec ("Đơn giản hoá Bình luận ghim + sửa lỗi trùng số thứ tự"). **Replaces** the free
template of [2026-11-14-pinned-comment-template](2026-11-14-pinned-comment-template.md); its other points (built
when shown, never stored; warnings never blocking) stay.

- **Why.** The script prompt puts a number before each scene's name ("1. CÀ TÍM + ĐẬU ĐŨA") and `{items}` numbered
  it again ("1. 1. CÀ TÍM..."); and the template with its six variable buttons was more than the team used: every
  pinned comment had the same shape.
- **Built.** The comment is always the title, the content scenes one per line, then "Dòng khảo sát"
  (`videos.pinned_survey`, migration 0110), each left out when empty ([pinned.py](../../api/src/reels_api/pinned.py),
  its twin [pinned.ts](../../web/src/lib/pinned.ts) for the live preview). A scene's name is the first line of its
  text with the number before it dropped (only when a mark follows the number: "1.", "2)", "3 -", "#4:", "Cặp 5:"),
  then numbered again from 1, so reordering or deleting scenes renumbers the list and a scene with no number still
  gets one.
- **Only the name, no "– benefit".** As the spec's example shows, a scene's other lines are no longer added after
  its name.
- **Survey line.** A new script's is the AI's question (the output format already asks for one); a video with none
  (written by hand, cloned, or a script without a question) starts with "Bạn hay ăn cặp nào nhất? Bình luận số thứ
  tự nhé". Emptying it leaves the title and the list.
- **Every video has a pinned comment now:** emptying the old template used to mean "no pinned comment"; the title
  and the scenes are always there now.
- **Migration.** A video's survey line is the first line after `{items}` in its old template that has no variable;
  any other video takes the default. `videos.pinned_comment` is kept, no longer read or written, so the change can
  be undone; a later migration may drop it.
- **Removed:** the template field, the variables `{title}`, `{items}`, `{item_names}`, `{count}`, `{hook}`,
  `{products}`, their buttons and the "?" help, the orange "no longer follows the scenes" line, and the checks for a
  hand-typed list (a numbered line matching no scene, a missing scene, scenes out of order), which can no longer
  happen. The API field is `pinned_survey` (PATCH `/api/videos/{id}`, MCP `update_video`); `pinned_comment_text`
  stays the whole comment.
