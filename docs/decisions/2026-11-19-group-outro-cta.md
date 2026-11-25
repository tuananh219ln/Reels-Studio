# 2026-11-19 — "Cảnh kết Theo dõi & Chia sẻ": a group switch, rendered once

Owner's spec ("Cảnh kết Theo dõi & Chia sẻ", a 4.5 s HTML + GSAP outro with narration and a "Ting"). Asked in the
session: a switch per topic group (not always on for MCP videos, not per Page), and the outro **replaces** the
script's closing call to action rather than following it.

- **Every way of writing a new video of the group gets it** (hand-written, the team's script job, "Nhân bản", "Từ
  video mẫu", MCP from the group's prompt). Videos that already exist are left alone; a member deletes the scene to
  drop it from one video.
- **"Replaces" is done twice:** the prompt asks the AI for no closing call to action (code, like the other format
  parts, since the outro is code), and a last content scene whose words still ask to follow, share, like, save or
  comment is deleted. A last scene that asks for nothing stays before the outro. The scene format has no "call to
  action" field, so the words are the only sign.
- **One render for every video.** The outro's markup is fixed, so its clip is identical on every video: the first
  outro scene gets an ordinary `motion` job from the worker's round, the clip is kept at a key named by the markup's
  hash, and later scenes copy it with no HyperFrames run. Changing the look in `outro.py` changes the hash and renders
  once more. Rendering it per video would have locked every new video for 1–3 minutes and clashed with the "Tự tìm
  ảnh" job (one job per video).
- **A person watches it.** The scene is a new look on every video of the group, so the PR is done only when a member
  has watched a sample MP4 with the outro against the spec and docs/ux-guidelines.md.
