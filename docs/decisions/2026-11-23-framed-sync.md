# 2026-11-23 — Every scene's photo and text start on one line

Asked by tuananh219ln after seeing two scenes of one video (a pomelo cut square, a guava a little wider than 4:3)
with their photos and texts in different places. A third round of
[2026-11-23-photo-framing](2026-11-23-photo-framing.md); it changes what that decision and
[2026-11-23-framed-zoom](2026-11-23-framed-zoom.md) built for the layout, not the framing itself.

- **One line for the whole video.** The tallest text box among the video's scenes whose photo is laid over its blurred
  copy (`reserve`) sets one block at the top of the safe zone (below the logo row when the logo is on); every such
  photo starts `GAP` below it, whatever its own text's height, and a scene with no text does the same. It replaces
  centring the text and photo as one group, which put each scene's photo at its own height. A text placed in the
  frame's lower half gets the mirror: the block at the safe zone's bottom edge, the photo above it.
- **The text is centred in its block**, so a one-line text, a three-line one and a 9:16 scene's all have the same
  middle line; the room a short text leaves is split above and below it, not left as a hole under it.
- **A photo that fills the frame ("Tự động" chose it, a 9:16) keeps its text on that same line**, instead of the
  template's place near the bottom, so the text does not jump when the scenes change. A scene set to "Lấp đầy khung"
  by hand, and the title scene, keep the template's place as before.
- **Square up to about 16:10 (1.6)**, from 4:3 (1.34): a photo like the guava (1.38) is cut square like the pomelo, so
  their scenes match. Wider ones (16:9) keep their shape, since a square would lose nearly half of them.
- **Changes the default for existing slide videos** (`image_fit` null is "Tự động"): rendered again they get the new
  layout, and their 9:16 scenes' text moves from the bottom to the top. As in the first round, the MP4 fingerprint
  does not change for it, so MP4s rendered before are not all marked "chưa cập nhật" at once.
- **No dark band behind text on a photo.** Text with no box or a see-through box over a bright 9:16 photo can be
  hard to read; a gradient band was tried and dropped for now (owner's call). Add it when it is needed.
- **Everything is worked out in one place:** `framing.plan_frame` takes `reserve`; the render finds it from its
  scenes (`render.py`), the api from the video's scenes (`videos.text_reserve`) for the previews, the drag frame and
  `image_frame.text_at`, so they agree. A scene's frame address includes `reserve`, so another scene's taller text
  draws it again.
