# PC Shopee text sizes: smaller, in proportion

Title tiers (small / main / sub, px on 1080x1920): default 52/104/64; neon_tech_teal 52/100/56; neon_outline_price 56/128/56;
gold_metal 56/116/68; grunge_rainbow 64/104/60; esports_blue 56/112/64. Content scene: main 80, sub 54.

- **Why:** the old sizes made the title block about 250 px tall and the main line shrink to fit 88% of the width. The new ones keep
  the title block at most 15% of the frame, the scene block near 8%, every line at least 48 px, main : small at least 1.8 and
  main : sub at least 1.5 (grunge_rainbow's small line was nearly as big as its main line).
- **Still open:** estimates, to be compared by a person with a sample MP4 against docs/ux-guidelines.md.
- Replaces the sizes in [title-presets](2026-11-27-title-presets.md) ("the title keeps 56/110/72").
