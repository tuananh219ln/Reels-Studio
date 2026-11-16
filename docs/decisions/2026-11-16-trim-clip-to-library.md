# 2026-11-16 — Cut a library clip into a new library item; delete library items over MCP

Asked by the owner (namtc) on 2026-11-16 from [the brief](../specs/trim-clip-to-library/brief.md), after the library
rule of that day: the Kho tư liệu keeps only parts already cut to what a scene needs, tagged, never the whole
downloaded video. The owner chose to ship the web button and the MCP delete tool in the same change.

- **"Cắt thành file mới"** (`POST /api/media/{id}/cut`, MCP `cut_clip_to_library`, a button in a clip's details on
  `/media`): a part of 1–60 seconds of a library clip becomes a new clip item of the member's own, cut like a scene's
  footage (`clips.cut_part`, re-encoded, no sound: narration is its own track) and checked with `check_clip`. It takes
  a folder and at least one tag (video, scene, dish or topic): the library keeps no untagged cut. It keeps the clip's
  source link, for a copyright claim. Nothing is stored when the cut fails or runs past the clip's end.
- **The clip is never deleted or changed by a cut**, and a cut is never attached to a scene by itself: each step
  stays separate so it can be checked. Deleting is its own step.
- **MCP `delete_media`** deletes a library item through the existing `DELETE /api/media/{id}`: only the member who
  added it, and a scene that used it keeps its own copy. The brief thought no delete route existed; the web had one.
- **In the request, not the job queue**: one cut of at most 60 seconds takes a few seconds of FFmpeg, like a pasted
  link's download in the same router.
- A clip over a minute keeps only its first minute when it comes into the library (unchanged), so a part after that
  minute cannot be cut from the library copy.
- Unchanged: `use_in_scene` (a copy), the render reading `scene.video_key`, the footage flow.
