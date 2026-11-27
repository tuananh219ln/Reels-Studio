# 2026-11-27 — PC Shopee's compact text: the title in three tiers, a scene's text in two, "Trên / Dưới" (round 3 of the spec)

Part of the spec "Ẩn chữ & Phụ đề Cộng dồn" (Looper, 2026-11-27); looks are in [2026-11-27-pc-text-styles.md](2026-11-27-pc-text-styles.md).

- **Two options, `title_layout` (`box` | `three_tier`) and `scene_text_layout` (`box` | `two_tier`)**; a new PC Shopee video starts
  with both compact. Every other group keeps the boxes: the options are `box` for them and the MP4 fingerprint leaves them out.
- **The tiers come from the text already there, no new fields.** The title's lines are read as small / main / sub (one line is
  the main one, two are main and sub, three or more small, main and sub), and a line written `[[-50%]]` is the orange label.
  The page shows them as four boxes (Dòng nhỏ, Dòng chính, Dòng phụ, Nhãn) that write the title's text back. A small line needs
  a sub line too (two lines are read as main and sub). A scene's text: the `*marked*` words are the main line, the rest the sub
  line, a leading "3." the orange numbered circle. The spec's "AI suggests the three lines" is **not built**: the full title
  and the caption are untouched, and a member (or their assistant through MCP) writes the tiers.
- **Limits warn, never block:** a title line over 14 characters, a scene's main line over 16 or sub line over 4 words give a
  yellow warning (`videos.tier_warnings`); the line is shrunk to fit 88% of the width (title) or 92% (scene) and renders.
- **The last scene (the call to action) and every other group keep the text box.** The title block is at most about 22% of the
  frame and centred 22% down; a scene's block sits at 62–78%, or in the 14–30% zone when the scene is set to "Trên"
  (`scenes.text_zone`, migration 0141; also used by the "Cộng dồn" captions). A text dragged to a place keeps it.
- **No entrance animation yet** (the title's bounce, the numbered circle's pop): a picture that animates needs a looped input
  per picture on a render that already lays many; the text shows at once. "Ẩn chữ sau X giây" still applies to the scenes'
  tiers, since they are laid as the scene's text picture.
- **The studio's previews, the drag box and the thumbnail follow the tiers** (`frames.compose_frame`/`text_box`, which take
  whether the scene is the last, its zone and its narration): the title's thumbnail is the three tiers, a content scene's
  preview the two, and under "Cộng dồn" a scene's preview shows the first phrase whole and drawn still (the MP4 plays the words
  in), with no text box to drag. The preview addresses carry these only while they are in use, so other videos' stay valid.
- **The studio's player plays "Cộng dồn"** (`/scenes/<id>/cumulative`, `CumulativeStage`): the steps are the render's own pictures, laid
  over the scene at their seconds as the layers are (the words at ElevenLabs' real seconds once the narration has them, else the
  estimate over the made narration's length). The preview picture of such a scene has no phrase drawn into it (`preview.jpg?live=true`);
  the timeline's "Chữ" track skips a scene whose text "Cộng dồn" replaces.
- **A group holds PC Shopee's settings in its "Chữ & phụ đề"** (`text_looks.PC_FIELDS`, with "cumulative" captions): only for the group
  PC Shopee (the api refuses them on any other, a stored look read back drops them), shown in its card on Kho kiến thức, and over the
  starting values a new PC Shopee video takes. The AI that suggests or picks a look is never asked for them nor accepts them. They are
  **not** on Cài đặt › Thiết lập mặc định, which is a member's defaults for every group.
- **The assistant** sets them with `set_video_options` (text_hold_sec, pc_style, pc_title_style, title_layout, scene_text_layout) and
  `set_scene_effects` (text_hold_sec, text_zone).
- **Changed after the first videos (2026-11-27):** a scene's text roles follow the team's own texts, where the name is on the first
  line and the `*marked*` words highlight the benefit. With two lines or more the **first line is the big one** (the product) and the rest
  the sub line, however the words are marked; the spec's "the marked words are the main line" applies only to a single line
  (`*LOGITECH G304* không dây`). And the compact text and **phrase or word captions are never on screen together**: with no hold
  chosen, the text goes after 2.5 s and the captions start then (`text_hold`, `captions.after_hold`); a hold the member chose wins.
