# 2026-11-23 — A framed photo zooms inside its box, its blurred copy half as far

Asked by tuananh219ln, as the next round of [2026-11-23-photo-framing](2026-11-23-photo-framing.md) (spec section 7:
the photo 1.00→1.06, the blurred copy 1.00→1.03, the text still).

- **Two layers in the render:** a framed photo reaches FFmpeg as its blurred copy (with the shadow) at 1080×1920 and
  the photo alone, laid in its box ([graph.py](../../worker/src/reels_render/graph.py) `FramedInput`). Each runs
  through its own `zoompan`, then the colour preset grades them together.
- **The photo zooms inside its box, which never moves.** Zooming the whole built frame (round 1) pushed the photo's
  top edge up towards the text box (about 50 px at the default 1.12); now the gap stays as laid out.
- **Shares of the video's own zoom, not fixed numbers:** the photo moves at half the video's zoom and the copy at a
  quarter (`framing.PHOTO_ZOOM_SHARE`, `BACKDROP_ZOOM_SHARE`), with the video's own motion (zoom in or out, pan,
  handheld...). At the default "medium" (1.12) that is the spec's 1.06 and 1.03; "static" keeps both still.
- **The box and its place are even numbers**, so the photo lines up with the MP4's half-size colour planes.
- **The first frame is unchanged:** zoom 1.00 of both layers is the frame the previews draw (`framing.compose`).
