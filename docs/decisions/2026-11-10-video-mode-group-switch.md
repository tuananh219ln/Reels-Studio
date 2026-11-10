# 2026-11-10 — "Kiểu video" is a topic group's setting, with "Xen kẽ theo ngày"; a video's own choice wins

Brief [docs/specs/mcp-video-mode](../specs/mcp-video-mode/brief.md), the owner's (namtc) decision of 2026-11-10:
his two Pages alternate the two kinds of video in phase 1, and the rule must sit on the topic group, not in each
tool's instructions, so every way of making a video gives the same kind. Extends "Kiểu video" (2026-11-07 in
[decisions.md](../decisions.md)); `Video.mode` and the render are unchanged.

- **A switch per topic group** (`knowledge_topics.video_mode`, migration 0073) with three settings: `slides`
  ("Slide ảnh"), `single` ("Video xuyên suốt") and `alternate` ("Xen kẽ theo ngày": an odd calendar day in
  Asia/Ho_Chi_Minh makes `single`, an even one `slides`; the day of the month, so the 31st and the 1st are both odd).
  Every group, old and new, starts on `slides`: nothing changes until its owner switches it on Kho kiến thức; no
  group is switched by the migration.
- **The order:** the mode asked for the one video › the group's switch › `slides`.
- **One place decides it:** `routes_videos.start_video`, which every way of making a video goes through (the web's
  "Tạo video", the team's AI and the assistant through MCP, the semi-automatic round). The round passes the day it
  prepares, so a video made at 08:00 is that day's kind whatever the clock says later. The MCP tools take
  `video_mode` as optional (none: the group's); `get_script_prompt` answers with the mode resolved, so the script is
  written in that mode's format and sent back with it.
- **Not through the group:** "Từ video mẫu" (its scenes are cut from the sample, and it never had a kind to pick)
  and a clone or a platform version (it keeps its source's), as before.
- The switch follows the group's other settings: in its history ("Lịch sử") and behind "Cho cả đội sửa".
