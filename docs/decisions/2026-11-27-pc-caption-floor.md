# 2026-11-27 — PC Shopee's phrase and word captions sit on the safe zone's floor (issue #385)

- **In a scene with the compact text** (`scene_text_layout` = `two_tier`), "Từng cụm" and "Từng từ" captions have their bottom at
  y = 1440, the safe zone's floor, not just above the text (`render.tier_caption_y`). The text has gone by the time they start
  ([pc-text-tiers](2026-11-27-pc-text-tiers.md): hidden after 2.5 s, or the hold the member chose), so they do not need to dodge it.
- **If the text stays the whole scene** (a member set no hold on a scene where it would otherwise be hidden) and the caption would land
  on it, for example after dragging it low, the caption goes over the text as every other scene's does, or under it when that leaves
  the safe zone, so the two never overlap.
- **The studio's preview draws no phrase or word captions** (they only come with a render, as its header says), so it cannot disagree
  with the MP4 about them; "Cộng dồn" is the render's own pictures. Nothing changes on the web.
- **The last scene (the call to action) follows too:** it keeps its text box, but under the compact text its captions also sit on the
  floor (y = 1440) instead of following the box wherever it was put, so they no longer jump to the top in the last scene. The rule
  applies to every content scene of a video with `scene_text_layout` = `two_tier`; the box, which stays all scene, is still dodged.
