# 2026-11-27 — The "Neon xanh ngọc" look is removed

It looked almost the same as Neon game: same teal glow and dark outline, and its font (Audiowide) has no Vietnamese marks, so every
Vietnamese line fell back to Saira and lost the only visible difference. Neon game is the default and has all the marks.

- Taken out like [Halftone tím](2026-11-27-remove-halftone-look.md): the render, the pickers, the api's values and the guide. A video
  that still has `neon_tech_teal` reads as "Neon game" (`video_options.REMOVED_STYLES`); no migration.
- Audiowide stays for "Giá neon viền". Four title presets are left: Giá neon viền, Vàng kim loại, Grunge cầu vồng, Esports xanh.

- **"Thương hiệu" gets Neon game's glow in its own colours (same day):** the letters keep the brand's yellow and white with the navy
  outline, and the hard offset shadow is replaced by a soft glow of the letter's own colour (yellow around the marked words, white
  around the others), as Neon game has a glow. The colours are unchanged.
