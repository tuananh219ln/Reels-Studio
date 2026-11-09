# 2026-11-09 — The assistant sees, puts on and saves "Mẫu dựng" through MCP

Part 5 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md), the owner's brief of
2026-11-09: the daily build runs through MCP, which had no tool for templates. Extends "The assistant edits like the
studio and checks its own frames" (2026-11-07) with three tools, modelled on `set_video_options`.

- `list_templates` (`reels:read`): the app's own, the member's own and those a topic group holds, not a teammate's
  that no group holds, each with its scope, its groups and the parts to pick by. A template holds no kind of video,
  so `video_mode` is always null.
- `apply_template_to_video` (`reels:write`): the web's own apply, so it is the template chosen on the video (top of
  the order of the entry "A topic group holds its own Mẫu dựng…" of the same day), replaces the one the video wore,
  and keeps the call to action free of the template's end line.
- `save_video_as_template` (`reels:write`): into the member's own templates only, never a group's. Template names are
  unique across the team (`edit_templates.name`, since 2026-11-05), so a name taken by anyone is refused and nothing
  is overwritten.
- The server picks no template by itself: choosing and saving are the assistant's, by the rules written in the tools'
  descriptions. No deleting or editing a template through MCP yet; when it comes, it follows "What a member made, only
  they delete".
