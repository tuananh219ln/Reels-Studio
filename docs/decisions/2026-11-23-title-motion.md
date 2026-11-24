# 2026-11-23 — "Tiêu đề động": built on the motion scene, slot photos in one atlas

Owner's spec "Tiêu đề động 3 giây" (phase 1, the "Sức khỏe" groups).

- **Reuses the motion job.** The title scene gets an ordinary `motion` job (one job per video, HyperFrames, render
  machines); no new job kind, no change to the render core. The slot photos are packed into one JPEG atlas shown as
  `assets/photo.jpg`, the "ảnh ghép" way the spec allows, instead of `slot_N.jpg` files, so the render machine bundle
  stays one photo.
- **Cổ điển / Động is stored in `scenes.motion`** (`title`, `classic`, `clip_seconds`), not in new columns: no
  migration. The title's old photo or clip is kept (`motion.attach` no longer deletes it), and the switch swaps
  the scene's media fields without a render.
- **Missing photos refuse the build** (422 naming the scene) rather than showing placeholders.
- **The hook is written only when asked** (empty title, or "Viết lại chữ tiêu đề theo mẫu"): a member's own title is
  never overwritten silently. Its narration (`hook_voice`) is written with it.
- **Cropping is a heuristic.** No object detector is installed, so a slot is cut around the sharp, colourful part
  of the photo (`subject_centre`), halfway back to the middle. A member can aim it (`focus`) or take the photo from
  another scene (`from_scene`) through the API.
- **A slot's own photo** (upload, link or library, `slots[i].image_key`) is kept by rebuilds and shows from the next
  build; the web panel offers upload and link, the library through the API only.
- **"Mặc định theo Page" lives on the channel (`brands.title_style`, migration 0122).** The spec did not say when it
  applies; a video is tied to a Page only through its channel ("Kênh"), so the setting sits there beside "Video của
  Page tự gắn logo". It decides what a title shows after its **first** build (Cổ điển keeps the photo or clip, the
  clip is still made and kept); it never builds a title by itself and never overrides a switch a member made.
- **Left out of this round:** checking video 259 against `tieu_de_259_mau_chuan.html` (needs the production video,
  which agents must not touch). A person watching the sample MP4 is still required before merging.
