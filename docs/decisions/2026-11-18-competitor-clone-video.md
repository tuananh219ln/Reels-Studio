# 2026-11-18 — "Clone" a competitor's video into a hand-written draft

From the owner's brief "Nút Clone cạnh mỗi video đối thủ" (2026-11-18). Builds on
[the competitor analyzer](2026-11-17-competitor-analyzer.md), [team read](2026-11-17-competitor-team-read.md) and
[v2](2026-11-18-competitors-ui-v2.md), all of which stand.

- **Clone is built in code, never by AI, and costs nothing.** One click makes a "Tự viết" (`hand_written`) video in
  the chosen group from the caption the scan read (`clone.clone_script`); no job is queued, no render. Photos, clips,
  narration and rendering are done by hand on the video's page, as for any "Tự viết" video. A member who wants the
  ideas rewritten asks their own Claude through MCP (`competitor_video_details`, `update_scene`); no new MCP tool.
- **"Y hệt" means the caption, title and scenes.** The caption's first sentence is the title and the hook; each idea or
  list item that follows is a scene; a closing call to follow or save is a scene of its own. Hashtags, emoji and
  "Xem thêm" are dropped. A caption that is only a title gives a hook and a closing scene, flagged `thin`. A video
  without a caption cannot be cloned (no guessing at its content).
- **Comments are for understanding, never part of the script.** They are shown in the dialog and, folded, on the
  cloned video's page; they are read from the competitor's video (not copied to the new one) and go when the
  competitor is deleted.
- **The source is kept as text.** `videos.competitor_source_url` (only a `https://www.facebook.com/` link),
  `competitor_source_name` (the channel's name then) and `competitor_source_video_id` (`ON DELETE SET NULL`). Named
  `competitor_source_*`, not the brief's `clone_source_*`, because `videos.clone_source` already holds "Nhân bản"
  (the AI clone of one of our own videos). Nothing of the competitor's media is downloaded or copied.
- **"Quét bình luận video này" is a comments scan on demand**, the brief's open question 1 answered as it proposed:
  only when asked, not for the whole channel. It is a `meta_only` scan (never a latest scan for numbers) whose scope
  names the videos (`comments_for`) and the scan they belong to (`source_scan_id`); comments replace that scan's
  sample as in M4, text and likes only. Only the member who scans the competitor queues it, and their open page runs
  it with the extension they have: the page asks for one grid card (ignored), then the extension opens the named
  videos as after any grid. **No new extension version is needed**, so `extension/` is unchanged.
- **Only in each channel's video list** (open question 2): not in reports or "So sánh" for now.
- Any member clones any of the team's competitors' videos; the new video is theirs. At most 20 clones a minute per
  member, against repeated clicks.
