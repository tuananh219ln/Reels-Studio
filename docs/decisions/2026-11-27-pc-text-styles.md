# 2026-11-27 — Three looks for PC Shopee's drawn text: Neon game, Halftone tím, Thương hiệu (round 2 of the spec)

Part of the spec "Ẩn chữ & Phụ đề Cộng dồn" (Looper, 2026-11-27); see [2026-11-27-cumulative-captions.md](2026-11-27-cumulative-captions.md).

- **One drawing module for all PC Shopee text** (`reels_render/pc_text.py`): a line of capitals drawn as a picture with its
  fill, outline(s), shadow and glow by role (a marked word or a plain one). The captions, the scenes' two tiers and the
  title's three tiers all use it, so they match. A new option `pc_style` (captions and scenes' text) and `pc_title_style` (the
  title; default `brand_navy`), both of `PC_STYLES`.
- **Neon game** (default): Bungee (OFL, bundled), white, marked words `#5EF2D0`, 6 px `#0B1E2B` outline, `#3FE0FF` glow at 55%.
  **Thương hiệu**: Be Vietnam Pro Black, white `#FEFFFA`, marked words a `#FFD84A` to `#FFB113` gold, 6 px `#10195E` outline and a
  6 px hard shadow. **Halftone tím**: Be Vietnam Pro Black, lines alternate black and light grey with halftone dots drawn in code
  (no PNG tile), the marked line has a lavender-to-mint outline; its colours are the spec's estimates from a screenshot and
  **still need comparing with the sample**, which only a person can do. Its three lines are not made 100/92/85% apart: the
  captions keep the Neon sizes, the title uses the spec's sizes.
- **Font choice:** Bungee has every Vietnamese mark tested ("ĐÁNG SĂN", "Ổ CỨNG", "MÀN HÌNH", Đ Ă Ơ Ư Ị Ổ Ự and the
  rest); Dela Gothic One was not tried, Be Vietnam Pro Black is the font the app already ships.
- Chosen on the video's Thiết lập for PC Shopee only; the fingerprint holds the look only when it is not the default.
