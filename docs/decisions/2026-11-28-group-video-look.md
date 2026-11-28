# 2026-11-28 — A topic group's own motion and sound ("Chuyển động & âm thanh")

Asked by tuananh219ln: editing style is set per topic group, as its voice, video mode and "Chữ & phụ đề" already are.

- **`knowledge_topics.video_look`** (migration 0142) holds any of: transition, motion, zoom, narration on or off,
  reading speed, voice volume, pause after narration, "Nhỏ nhạc khi có giọng", music volume, and the background music
  (`video_options.GROUP_VIDEO_FIELDS`). Null: the group sets nothing, as every group before.
- **Music has three choices:** the maker's own (the key left out), one library track from a chosen second, or none. A
  track claimed on YouTube or deleted since leaves the maker's own, so a new video is not silent by surprise.
- **"Chữ & phụ đề" now saves its two checkboxes**, "Nền tối mờ sau chữ" and the title look's frame effects: the card
  showed them but the api refused them, so ticking did nothing. A look saved before holds neither, and its videos keep
  their maker's.
- **New videos only**, in the order the other group settings use: the video's own › the group's › its maker's defaults ›
  the app's. Existing videos never change. A "Mẫu dựng" or the AI's effects still set scenes' own transitions over it.
- **A card of its own on "Cài đặt nhóm"**, off by default; switched on it starts from the member's own defaults and saves
  every field. Kept apart from "Chữ & phụ đề", so saving one never rewrites the other. In the group's history, copied by
  "Nhân bản nhóm", edited by whoever may edit the group.
- **Not in this change:** the safe-zone profile and the text's place per group (not asked for), and editing it through the
  assistant (MCP).
