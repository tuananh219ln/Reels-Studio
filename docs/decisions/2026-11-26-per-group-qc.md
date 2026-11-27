# 2026-11-26 — QC by group, a free title choice, and a video's edit history with undo

Asked by the owner (namtc) from the brief [docs/specs/per-group-qc/brief.md](../specs/per-group-qc/brief.md), after the
review gate ([2026-11-26-review-gate](2026-11-26-review-gate.md)) went live: every Topic Threads video was blocked by an
empty title (its title is drawn in the OP card, by the format's rule) and every video carried the same length and scene
warnings each day, so "Vẫn duyệt" became a reflex. Chosen with the owner: one PR for all of it.

## Decision

- **A group's QC is a group setting in the database**, as "Mô tả YouTube" ([2026-11-25](2026-11-25-youtube-description.md)):
  `knowledge_topics.qc_config` ([qc_config.py](../../api/src/reels_api/qc_config.py), migration 0136), edited on Kho
  kiến thức › Cài đặt nhóm › QC & duyệt or through MCP `get_qc_config` / `update_qc_config`, followed in the group's
  history and copied by "Nhân bản nhóm". Fields: `title_required`, `total_seconds`, `scene_count`, `channel_seconds`.
  A group with nothing set (None) checks exactly as before; only the fields that differ from the defaults are saved, so
  a later change of a default still reaches it. Topic Threads starts at no title, 45–100 s, 5–13 scenes, MP4 60–90 s;
  every other group starts empty.
- **This relaxes two logged decisions, by group only:** "an empty title" as a `blocker` of
  [2026-11-26-review-gate](2026-11-26-review-gate.md) holds unless the group sets `title_required` false or the video
  has "Không dùng tiêu đề"; "the yellow warning stays at 20–55 seconds" of
  [2026-11-20-total-length-150](2026-11-20-total-length-150.md) is now the default of a range each group may change.
  The hard cap of 150 seconds is unchanged for every group.
- **The MP4's length is judged when read**, from `videos.mp4_seconds` against the group's range
  (`qc.rejudge_length`), so videos rendered before a range changed follow it without a render.
- **The loudness target stays one for every group** (−14 LUFS, the platforms'), on purpose.
- **No "turn off the short-clip warning" setting.** "Video ngắn hơn cảnh" is already off for a scene with "Lặp clip",
  and when it shows the last frame really holds. MCP `update_scene` takes `video_loop` instead.
- **The title is free:** a suggestion, typed by hand, or "Không dùng tiêu đề" (`videos.no_title`; the text kept in
  `videos.kept_title` and given back when unticked; typing a title unticks it). The web's title picker and the MCP tool
  `set_video_title` do the three. The rule of `docs/specs/web-video-render/user-spec.md` (the title is the title scene's
  text; the suggestions never change) holds.
- **A video's edits are logged** in `edit_logs` (`entity_type` `video`, a scene's fields as `scene:<id>:<field>`),
  extending [2026-11-09-edit-history](2026-11-09-edit-history.md), with `source` `web` or `mcp`. "Lịch sử sửa" on the
  video page lists them; "Hoàn tác" puts an edit's old values back through the same edit routes, as a new `restore`
  entry, and refuses when the place was edited since (no overwrite) or the scene is gone. Not logged yet: photos and
  clips, adding, deleting and reordering scenes. A keyboard Ctrl+Z is left for later (it touches every field of the page).
- **"Video này được làm như thế nào"** reads only what is already stored: the maker and how the script was written, each
  scene's voice and its source (ElevenLabs, VieNeu, Gemini, Google or an uploaded MP3), the music, the times, and one
  timeline of jobs, review steps (`video_events`) and edits. Edits made before this was deployed are not in it.
- **The group setting is the one source of truth** for a group's voices and QC. MCP `update_voice_format` lets an
  assistant change "Giọng đọc theo vai" (same editors and history as the web card), so a decision on voices is made
  there first and notes and briefs point to it instead of copying it.
