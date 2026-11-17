# 2026-11-17 — "Nhân bản xáo cảnh": copies with the scenes in another order, renumbered, title to change

From Looper's spec "Nhân bản video với xáo trộn cảnh", built by tuananh219ln's request in the session. The spec's
points below were settled against the app as it is.

- **Its own menu item and drawer, not a "Y hệt / Xáo trộn" radio** in a shared dialog: "Nhân bản y hệt" has no
  dialog and stays one click ([2026-11-14](2026-11-14-duplicate-video.md), unchanged), and "Nhân bản" is the AI clone.
  The copy is that exact copy (`duplicate.copy_video`) with the content scenes reordered, so no LLM call and no job.
- **The hook is the title scene's text**, which is also what lists and the "Tiêu đề" row show (the spec's open
  question). So one reminder, "Đổi tiêu đề", covers both; `videos.review_title` keeps the title the copy started with
  and the reminder lasts while the title scene still says it (compared without case, `*` marks and extra spaces) or
  until "Bỏ qua". No separate `needs_title_review` / `needs_hook_review` flags.
- **No `audio_stale` column:** a scene's narration is reused only while its signature (text, voice, speed) matches,
  so a renumbered voice text is read again at the next voice job or render by itself. Likewise a reshuffled copy's MP4
  shows "MP4 chưa cập nhật theo bản sửa" through the render fingerprint.
- **Renumbering** changes a list number only at the start of the on-screen text and the voice text, keeping its word
  ("Số", "Cách", "Món", "Bước", "#"), mark and spaces; a mark right before a digit ("1.5", "3-4") is not a list
  number. It runs when at least half the content scenes are numbered; numbers not 1, 2, 3… in order are still
  renumbered, with a warning.
- **Orders avoid** the source's, the first video's and every earlier copy's (`videos.scene_order`, kept as the first
  video's scene ids so copies of copies compare too). "Xáo lại cảnh" exists only on a copy.
- **New titles come from the member's assistant, not the team's AI** (tuananh219ln's choice in the session, over the
  spec's 5.1): the MCP tool `shuffle_duplicate_video` makes the copies and its description asks the assistant to
  write each a new title under the spec's rules (same idea and numbers, ±20% words, censorship spellings kept, each
  different, no emoji or hashtag) and save it with "Sửa cảnh". No job, no prompt in the app's data, no cost to the
  team's AI service. The web has no AI title button.
- **"Ghim cảnh khác"**: any content scene can keep its place, beside "Giữ cố định cảnh cuối", in the drawer, the api
  (`pinned_scene_ids`) and the MCP tool.
- **Left for later:** a QC item for an unchanged title.
