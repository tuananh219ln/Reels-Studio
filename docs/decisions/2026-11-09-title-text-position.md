# 2026-11-09 — The title box gets a video-wide place of its own (`title_text_position`)

User's decision, from video 64 checked through MCP on production: the video-wide `text_position` moves only the
content scenes, so the title box stayed in the middle of the frame and covered a face in the opening photo, and the
assistant had no way to move it (a title's own place can only be dragged on the web). Brief:
[docs/specs/title-text-position/brief.md](../specs/title-text-position/brief.md).

- A new video option `title_text_position` ([x, y], default None: the template's place, the middle of the frame)
  places the title box, like the other `title_*` options. Only y counts: the title stays centred across, as a place
  dragged on it already did (x is set to 1080 / 2), and the render core keeps it inside the safe zone.
- A place dragged on the title itself still wins. `text_position` keeps its meaning (content scenes only), so this
  extends, and does not reverse, "Text boxes can be dragged inside the platforms' safe zone": no existing video moves.
- Like `text_position`, it is left out of the MP4 fingerprint while unset, so MP4s rendered before stay current, and
  stored videos need no migration (`effective()` fills the new key with None).
- The assistant sets it with `set_video_options(title_text_position=[x, y])` and clears it with a flag of its own,
  `reset_title_text_position`, rather than widening `reset_text_position`, so each reset clears only its own place.
- Rejected: letting the title follow `text_position`. Smallest change, but every video that already moved its scenes'
  text would see its title box jump at its next render.
- Not on the web page in this round; a control next to the other title settings can follow in its own PR.
