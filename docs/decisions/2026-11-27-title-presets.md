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
- **Not built yet:** `frameEffects` (RGB split, vignette, sparkles), texture images (gold uses a gradient, the spec's `fallback`),
  the superscript "PHP", negative line gaps, per-preset font sizes (the title keeps 56/110/72), and the "Kiểu tiêu đề" thumbnails.
  Colours and sizes are estimates from the spec's table (`title-presets.json` was not in the repo) and need a person to compare them
  with the five reels.
