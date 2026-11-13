# 2026-11-13 — Footage tools for the always-on assistant (MCP)

The owner (namtc) runs an always-on assistant (Muse, over WhatsApp) connected to the Reels Studio MCP and wants
footage filled automatically without the team's API paying for frame selection. The worker cannot call an MCP
(a client session is needed), so the assistant does the looking.

- Three MCP tools: `list_scenes_missing_media`, `find_scene_footage`, `use_scene_footage`
  ([footage_tools.py](../../api/src/reels_api/footage_tools.py)). No LLM call of the team's and no job is made.
- Candidates are downloaded by the api into a one-hour cache (`$TMPDIR/reels_footage_candidates`, at most 30,
  random 16-hex ids, bound to one scene); `use_scene_footage` re-probes and cuts the same way as the automatic job
  (`auto_footage.attach`, now shared), so the silent clip, source link and "check again" mark are identical.
  The cache is per api host: a candidate is lost if the api restarts or a request lands on another instance, and
  the assistant just searches again.
- Same sources and limits as the job: public YouTube (bounded `yt-dlp`) and Pexels/Pixabay videos; no TikTok or
  Facebook search. A search is bounded by a 100-second download budget and two candidates.
- The automatic switch stays; the two paths are alternatives. The ready-to-paste routine is
  [muse-footage.md](../muse-footage.md). Whether Muse can run on a timer is up to Muse; the routine also works
  when sent by message.
