# 2026-11-10 — The video page shows where the video stands, with its times

Asked by the owner (namtc) on 2026-11-10: the video page had every editing detail but not where the video stands or
when anything happened ("thiếu cả thời gian nữa"); the times go on the progress line rather than a block of their own
("Gộp với dòng tiến độ").

- **A progress line under the title**: Kịch bản → Ảnh → Render → Đăng → Affiliate → 48 giờ, each with its state and
  time (docs/ux-guidelines.md, Video editor). It reads only what the video payload carries, plus `script_at` (the last
  finished script job's end, or the video's making for a script written by hand or sent over MCP).
- **"MP4 cũ hơn bản sửa"** comes from the existing render signature (`mp4_outdated`), not from edit times.
- **"Sửa lần cuối" is left out**: a video's edits (scenes, layers, sounds, MCP) are not logged and the video has no
  `updated_at`; showing it needs a new column set on every edit path, a change of its own.
- **Affiliate counts as a step**: a video without products earns nothing, so it shows orange until one is attached.
