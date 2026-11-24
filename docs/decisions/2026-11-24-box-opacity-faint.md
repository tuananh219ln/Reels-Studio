# 2026-11-24 — "Rất trong": a box that lets 55% of the photo through

Asked by tuananh219ln after seeing a scene's text drawn outlined (no box) over a busy photo: hard to read, and a
solid box hides too much of the photo.

- **A new box opacity, `faint` ("Rất trong"): 45% of the box colour (alpha 115).** Next to Đặc 100%, Hơi trong 88% and
  Trong 70%. With a near-black box (the "dark" style, or "box" with `#111111`) it dims only the photo behind the text.
- **Only the text of the scenes**: it is one more choice of `box_opacity`, so it applies where a member picks it. The
  title scene has its own `title_box_opacity` ("same" by default) and the motion title its own shade; neither changes.
- **Black, not white**: the letters are white (marked words yellow), which read best on black; a white veil would wash
  out a bright photo and sink white letters.
- **Not a default and not a gradient band.** Videos made before render as they did; the band over the whole frame
  that [2026-11-23-framed-sync](2026-11-23-framed-sync.md) dropped stays dropped.
- **A person watches the render** before it is called done: 45% may be too faint over a very bright photo; if so the
  value goes up (55-60%).
