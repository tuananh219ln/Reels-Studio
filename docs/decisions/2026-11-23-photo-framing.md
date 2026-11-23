# 2026-11-23 — A wide photo is laid over its blurred copy instead of cut to fill the frame ("Khung ảnh")

Asked by tuananh219ln, with a written spec (SPEC_anh_nen_mo_HD, video 259, scene 2047 "1. Bưởi"): a 5:4 photo blown
up to fill 9:16 loses both sides and turns grainy, and the scene's text ends up on the food.

This changes the 9:16 cover crop that [2026-11-02](../decisions.md) kept for every photo ("the render core, its 9:16
cover crop and the database are unchanged"). It is changed on purpose, for a content scene's photo on a slide video
only; "Chỉnh khung" still crops in the browser, and a photo cropped to 9:16 there still fills the frame as before.

- **Round 1 is Pillow only** ([framing.py](../../worker/src/reels_render/framing.py)), shared by the render and the
  app's previews so both show the same frame. The spec's AI upscaling (Real-ESRGAN) and subject detection
  (GroundingDINO / OWL-ViT) are left for later: they need models of tens to hundreds of MB and minutes of CPU per
  video on the worker. "Nâng HD" is Lanczos plus an unsharp mask for a photo enlarged to the frame.
- **"Tự động" by the photo's shape:** narrower than 3:4 fills the frame (cover, as always); 3:4 to about 4:3 is cut
  square (the square slides along the longer side: "Dịch khung vuông", `scenes.image_crop_offset`, the middle when
  unset); wider keeps its shape. Both lie across the full 1080 px width over the same photo, covered, ×1.08, blurred,
  10% more colourful and 30% darker, with a soft shadow under it. No black bars, no rounded card.
- **The text goes above the photo, or below it when it was placed in the frame's lower half.** The text box's own
  place (the scene's or the video's "Vị trí chữ") only says above or below; where the photo goes then depends only on
  that and the box's height, so every square scene of a video with the same text height lands at the same place.
  Nobody placed it: above (the spec's "auto"), centred on the blurred part. The logo's row (370 px) is kept as the
  render already did.
- **No `text_anchor` field:** the spec's anchor is read from the existing text position (upper or lower half), so
  "Lưu cho mọi cảnh" keeps working as an anchor for every scene without a new setting.
- **A 9:16 frame padded with its own blur** (a photo stored before this, like scene 2047) has its sharp band taken out
  first, so it is not padded twice. Only near-9:16 photos are checked; rows are compared with the top and bottom tenth.
- **Default on:** `image_fit` null means "Tự động", so a re-render of an existing slide video frames its wide photos
  the new way. The MP4 fingerprint changes only when a member picks a fit or slides the square, so MP4s rendered
  before are not all marked "chưa cập nhật" at once. The title scene (the cover) and a backdrop video keep the cover.
- **Not done in round 1:** the "Ảnh mờ, nên thay ảnh khác" warning, per-layer zoom (the photo and its blurred copy
  zoom together, as one picture), a draggable square on the photo (the slider covers the one free axis), and the
  MCP tool's field for it.
