# 2026-11-27 — The "Halftone tím" look is removed

The team found it ugly. It was one of the first three looks of [pc-text-styles](2026-11-27-pc-text-styles.md).

- Taken out of the render (`pc_text.PC_STYLES`, its drawing and the halftone-dots code), the page's pickers, the api's accepted values and
  the in-app guide. The looks left are Neon game, Thương hiệu and the five title presets.
- **No migration:** a video that still has `halftone_purple` as its `pc_style` or `pc_title_style` reads as "Neon game"
  (`video_options.REMOVED_STYLES`, applied in `effective`, as old speed names are), so it renders and opens as before; a stored group
  look with it is dropped by the existing validation and the group falls back to the member's defaults. Saving the video writes the new value.
