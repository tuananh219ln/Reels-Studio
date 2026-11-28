# 2026-11-28 — Where text, captions and the logo go: one safe layout for every video

Asked by tuananh219ln from the spec "vị trí chữ, phụ đề và logo (mặc định cho mọi video)". The numbers come from real
TikTok screens, video 505's render and the figures Meta and Google publish for ads, so they are estimates for ordinary
posts and may change when the apps do.

- **The numbers live in one place, `reels_render/layout.py`**, as two profiles. The render, the previews, QC and the web
  (through the api's `layout` and `text_area`) all read them.
  - `balanced` (default; TikTok and Facebook Reels): text from y 290, x 65–1015, captions' bottom y 1530.
  - `universal` (also YouTube Shorts, Instagram Reels or an ad): the same top, x 65–888, captions' bottom y 1248.
  - Captions are at most 696 px wide (x 192–888). The logo's ring is 130 px with its top-left corner at (750, 660).
  - A video picks its profile with `layout_profile` ("Vùng an toàn" on Thiết lập, and `set_video_options`).
- **Places apply to every video; sizes, fonts and styles do not** (the owner's choice, the same day). The spec's table
  also changed the title and scene layout, the text sizes and the captions mode. Those stay as each video, member and
  topic group sets them, so PC Shopee keeps its compact text and "Cộng dồn".
- **A text nobody placed starts at y 290**, the title and the content scenes alike, whatever its height, centred across
  (moved left only when the profile's right edge asks for it). Captions end on the floor; when a scene's text is still
  on screen where they would land, they go just over it. A box is never wider than the profile's room (950 px, was 960;
  823 px on `universal`).
- **The compact text starts at the top too.** `scenes.text_zone` now holds "top", "bottom" or null, null meaning each
  thing's usual place: the compact text high, the "Cộng dồn" captions low (from 62% down, as before). "Dưới" puts the
  compact text where it used to be. A scene saved as null before reads as the new usual place.
- **A card ("Thẻ") or an inset photo that reaches up to the text's place sends the text to the bottom**: for the inset
  the mirror of the rule before; a card hangs from y 220, where text now goes. The MP4's fingerprint keeps the place the
  old inset rule gave, so MP4s rendered before stay current.
- **The logo moves under the text, top right**, and may be moved and resized for a video (`logo_position`, `logo_size`
  in the video's options, 80–240 px), one place for the whole video so it stays still through transitions (the owner's
  choice; the spec's "saved per scene" is not done for the logo). The title scene still has no logo, so the spec's
  "below the title" limit on dragging is not applied: the logo is kept inside the profile's edges and between y 290 and
  the captions' floor, and QC warns when it covers a content scene's text. Text no longer makes room for the logo.
- **QC warns only about what can go wrong.** The render clamps text, captions and the logo inside the edges, so the
  spec's "text above 290", "captions below the floor" and "logo outside x" cannot happen; the logo over a text is the
  warning.
- **Existing videos** keep their MP4 and are not marked outdated. Their next render uses the new places; a stored text
  place outside the edges (video 505's [540, 190]) is clamped. The thumbnail is drawn again with every render.
- **A render machine is always sent `layout_profile`**, so one on older code refuses a render instead of using the old
  places: update every render machine after deploying.

This replaces, for places only: "Text boxes can be dragged inside the platforms' safe zone" (2026-11-01, x 60–940,
y 220–1440), the logo's corner and text floor of [2026-11-13-brand-logo](2026-11-13-brand-logo.md), the text's template
places and the compact text's zones of [2026-11-27-pc-text-tiers](2026-11-27-pc-text-tiers.md), the captions' floor of
[2026-11-27-pc-caption-floor](2026-11-27-pc-caption-floor.md) (y 1440), and the inset's side rule of 2026-11-09.

Before this is merged a person renders a sample and tries it on TikTok (Đề xuất and Bạn bè) and Facebook Reels against
the spec's checklist; an agent cannot judge that.
