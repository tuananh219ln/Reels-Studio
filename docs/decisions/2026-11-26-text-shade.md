# 2026-11-26 — "Nền tối mờ sau chữ": a dark gradient band behind a content scene's text

Asked by tuananh219ln after seeing text drawn outlined over a busy photo (an omelette) that was hard to read.
[2026-11-23-framed-sync](2026-11-23-framed-sync.md) dropped a dark band "for now, add it when it is needed"; this
adds it, as a choice, not as a default. [2026-11-24-box-opacity-faint](2026-11-24-box-opacity-faint.md) ("Rất trong")
stays: that one is a box round the text, this one is a band behind it.

- **A black band across the frame's width, 45% at its darkest.** Full strength over the text's own rows, easing to 0
  over 260 px above and below (`textbox.SHADE_ALPHA`, `SHADE_FADE`). The rest of the photo is not touched.
- **Content scenes only.** The title scene (and the motion title, which has its own shade) has none.
- **A video choice, off by default** (`text_shade`, "Nền tối mờ sau chữ": Thiết lập of a video, Cài đặt › Mặc định video,
  `set_video_options`). Videos made before render as they did; the MP4 fingerprint holds it only while it is on.
- **Drawn the same everywhere.** The render lays the band and the text box as one picture (`textbox.with_shade`), so
  it fades with the text on a backdrop video; the previews, thumbnails and the assistant's frames draw it in
  `frames.compose_frame`. Captions still go by the text box's own corner.
- **A render machine on older code refuses it** (`text_shade` is sent only when on, like `backdrop`), so deploy the
  worker with the api.
- **A person watches the render** before this is called done: 45% over a very bright photo, and the band's reach, may
  need another value.
