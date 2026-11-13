# 2026-11-13 — Rework unpublished videos and align scripts with automatic footage

The owner (namtc) asked to fix both the scripts and the videos not yet posted so they suit automatic footage,
without finding links by hand. Builds on [automatic scene footage](2026-11-13-automatic-scene-footage.md).

- **Scripts**: the first Vietnamese and English keyword of a scene is now a filmable query (object + visible
  action/state); later keywords keep the object's name for photos. Benefits, disease names and "every dish in one
  frame" are not queries. Voices stay about the dish, not cooking steps (the existing voice rule is unchanged). The
  default script and clone prompts drop the Markdown scene table and ask for JSON only. Groups with their own
  prompt keep it; the code-owned format carries the keyword rule for every group.
- **Timing**: when footage can be selected, narration is made before the clip is cut, so the cut matches the real
  narration; voices are reused by the render. This replaces "script timing preserved" in the earlier decision.
- **Rework batch**: only the maker, only videos never posted, not being posted and not scheduled (a scheduled
  post must be cancelled first, since Facebook holds the old MP4), not keeping a clip's own sound, and with no
  job. Up to 50 per request, one job each; the page queue approval is withdrawn and the result is rendered but
  never posted, so a member reviews it again. Manual media is kept unless the member ticks "Thay cả ảnh/clip đã
  chọn tay". One LLM call per video for the script plus the footage selection calls; retries resume from
  checkpoints and refuse when the video changed in between.
- **Not done**: the rework prompt is not yet editable per group on `/knowledge`; no automatic re-scheduling of
  cancelled posts.
