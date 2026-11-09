# 2026-11-09 — A topic group holds its own "Mẫu dựng" and names one for its new videos; a video wears one at a time

Part 2 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md), the owner's brief of
2026-11-09: one account runs several Pages and topic groups, each with its own editing standard, and fixed every video
by hand.

- **A group holds several templates** (`knowledge_topic_templates`, migration 0066), picked from the saved ones on Kho
  kiến thức's "Mẫu dựng" tab, and names one for its new videos (`knowledge_topics.edit_template_default`: "app", one
  of its own, or none). No template is made for a group: they are still saved from a video. No rotation: the group's
  one stays until a member changes it.
- **The order**, for a video whose scenes were just written, whoever made it and however (the web, a plan's idea, MCP,
  a clone, the semi-automatic round): the template chosen on the video itself › its group's › its maker's own (the
  entry "“Mẫu cho video mới” is each member's own" of the same day) › none.
- **A video wears one template at a time** (`videos.edit_template`): putting another on, by hand ("Tự dựng"), through
  MCP or automatically, first takes the last one's sounds and end layers off; transitions and colour are replaced as
  before. So a template picked by hand on a video that took its group's replaces it instead of adding to it, as the
  brief's acceptance asks ("render ăn mẫu Y, không ăn X"). This changes "Tự dựng" for a video that already wore a
  template: before, a second one added its sounds to the first's. A template picked on the video is put back if its
  scenes are written again. Videos made before wear none, so nothing is taken off them.
- Editing a group's templates follows the group's other settings: any member may, as before.
