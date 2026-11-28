# 2026-11-28 — The logo goes back to the top right corner

Asked by tuananh219ln after seeing the [safe layout](2026-11-28-safe-layout.md) deployed: at (750, 660) the logo
looked adrift in the middle of the picture, mostly on scenes whose text is short or gone, and on the title scene, which
it was meant to sit under, it is never drawn. They asked for the high place it had before.

- **Default:** a 120 px ring at y 160, its right side on the profile's right edge (x 895 on `balanced`, 768 on
  `universal`). It ends at y 280, over the text's top (290), so it covers no text. The old place was y 200–320 at
  x 900; it moves up 40 px because text now starts at 290.
- **A video may drag it from y 120 down** (`layout.LOGO_TOP_MIN`) to the captions' floor, between the side edges.
- The platforms' own top bars may cover part of it, also as an ad (`universal`): accepted for a logo, as before the
  safe layout. Texts and captions keep their places.
- A card ("Thẻ") hung high and wide can pass under the logo, as it could before the safe layout.
- Existing MP4s are not marked outdated; the next render uses the new place. A place a member saved on a video stays.
- **Update render machines:** one still on the safe layout's first code accepts the render and draws the default logo
  at the old (750, 660).

This replaces, for the logo's default place, size and upper limit only, the logo line of
[2026-11-28-safe-layout](2026-11-28-safe-layout.md).
