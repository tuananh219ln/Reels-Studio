# 2026-11-27 — Five title presets for PC Shopee, with their fonts (spec "Preset kiểu chữ tiêu đề")

- **The presets are five more values of `pc_style` / `pc_title_style`** (`pc_text.PC_STYLES`): `neon_tech_teal`, `neon_outline_price`,
  `gold_metal`, `grunge_rainbow`, `esports_blue`. They reuse the existing pipeline (title tiers, scene tiers, "Cộng dồn" captions), so
  no new table or column. The video's Thiết lập picks them in a Select (eight looks do not fit a segmented control).
- **A preset's lines are the tiers by position:** the line the caller marks as main takes the preset's emphasis line, the first other
  line its upper line, any later one its lower line. A scene's text and the captions use the same looks.
- **Fonts bundled in `worker/.../fonts/`** (all OFL, Permanent Marker Apache 2.0, licences beside them): Audiowide, Anton, Oswald,
  Montserrat, Saira, Saira Condensed, Permanent Marker. Oswald, Montserrat and Saira are variable fonts (weight, Saira also width);
  Pillow sets the axes.
- **Vietnamese:** Audiowide and Permanent Marker have no Vietnamese marks (checked). A line with a mark outside ASCII is drawn with the
  preset's fallback (`LineStyle.vi`): Saira wdth 125 for Audiowide. **Open question from the spec:** Permanent Marker falls back to
  Be Vietnam Pro Black for now; a handwritten brush font with Vietnamese is still to be chosen.
- **Frame effects (Mẫu 4):** the glitch (red and blue shifted 6 px apart) and a vignette are one FFmpeg chain on the title scene
  (`pc_text.FRAME_EFFECTS`, applied after the text so the title is glitched too). The option `title_effects` (default on, shown
  under the title's look only for Grunge cầu vồng) switches them off; the text is the same either way. Sparkles are not built.
- **Textures are made in code, not bundled** (`LineStyle.speckle`): gold glitter and the grunge's dark specks are seeded random dots
  over the letters, so they are the same every render. The spec's texture images (`gold-glitter`, `grunge-white`) are not used; if a
  real PNG is wanted later it replaces `_speckle`.
- **Sparkles** (Gold): four-pointed stars drawn into the title's own picture, inside its padding, behind the letters; the same
  `title_effects` switch turns them off, and the thumbnail follows it (`text_look`). Mẫu 4's glitch stays an FFmpeg filter.
- **A line that would shrink under 70% is wrapped** at the space nearest its middle (the halves keep the role); then the whole block
  shrinks by one factor if it is still too wide. A line with no space shrinks as before.
- **The picker shows a sample of each preset** (`GET /api/title-presets/<style>.png`, drawn by `render_title` with sample text,
  cached): the five rows of the two "Kiểu chữ" selects have a picture under the name.
- **Not built:** sparkles on the other presets (the spec does not say which have them), and the spec's brush font with Vietnamese.
- **"Tiêu đề động" needs nothing** ([title-motion](2026-11-23-title-motion.md)): it is for the "Sức khỏe" groups, and its hook text is the
  title scene's own text, drawn by the render core, not part of the motion's markup. So a preset applies to it as to any title,
  and changing the preset does not need "Dựng lại tiêu đề" (the spec's section 6 line is moot).
