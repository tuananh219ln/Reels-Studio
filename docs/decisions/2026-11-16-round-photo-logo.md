# 2026-11-16 — The logo on an article's photo is a round badge with a white ring by default

Asked by tuananh219ln from a spec ("Spec: Logo tròn viền trắng & xem trước FB đúng ảnh", by Looper).

- **Shape, ring and shadow are per brand** (migration 0095): `photo_logo_shape` (`circle` default, `rounded`, `none` =
  the logo as before), `photo_logo_border` / `photo_logo_border_color` (white by default) and `photo_logo_shadow`,
  edited in "Logo trên ảnh bài viết". The badge is drawn by `photo_logo.badge` at the photo's full size (at most 2048 px
  on the long side, never enlarged), cover-fitted, 4x supersampled for a smooth edge, with the ring 6 % of its
  diameter (at least 4 px), the diameter at least 120 px and 16 px from the edge.
- **Size and margin now count the photo's short side**, not its width, so the logo looks the same on every shape of
  photo. Saved values keep their number.
- **Existing Pages become round on their next post** (the default is `circle`): photos not yet posted get the badge;
  posted ones are untouched. A Page that wants the old look picks "Giữ nguyên".
- **No new "rendered_url" / render_key / `POST .../render`** from the spec: the preview, the editor and the post already
  call the same `photo_logo.render` for the stored photo (decision 2026-11-15), so they show and post the same pixels,
  and a changed logo or setting reaches every unposted photo with nothing to invalidate. The spec's endpoints would
  keep a second copy that goes stale.
- The white logo for dark photos applies to "Giữ nguyên" only; a badge has its own ring.
- Not done: the size limits stay 3–40 % (the spec says 8–20 %), the default size stays 12 % (the spec says 14 %), so
  no saved Page changes size.
