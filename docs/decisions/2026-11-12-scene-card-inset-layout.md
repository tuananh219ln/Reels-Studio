# 2026-11-12 — The inset always shows the scene's photo; one place button; the "Ảnh chèn" block beside the button

Asked by tuananh219ln from a spec ("Đặc tả chỉnh sửa giao diện thẻ cảnh – Reels Studio", @Looper), with the owner's
answers to its open points in the same session. It **reverses part of
[2026-11-12 — inset square and place window](2026-11-12-inset-square-and-place-window.md)**, decided earlier the same
day:

- **The inset has no picture buttons of its own in the card.** The "Ảnh chèn" block keeps only its switch and the "Cỡ
  ảnh" slider; Tải lên, Kho, Tìm and AI, and the line "Đang dùng ảnh của cảnh…", are gone. The inset shows the scene's
  photo, so changing it with the scene's picture tools changes the inset too. This reverses "the inset gets a photo of
  its own from the card again" (owner's choice, to accept that no other photo can be used from the card).
- **Older insets with a photo of their own keep rendering it** (owner's choice, so finished videos do not change). The
  block says "Đang dùng ảnh riêng chọn từ trước." with "Dùng ảnh của cảnh", which lets the copy go
  (`scene_photo`, unchanged api). The api, the assistant and a script can still give an inset its own photo; only the
  web's buttons went.
- **One button, "Chỉnh vị trí chữ & ảnh chèn"**, replaces "Chỉnh vị trí chữ" and "Chỉnh vị trí ảnh chèn (kéo lên
  xuống)". It opens the same window on the Chữ tab; pressing the dimmed one picks it and drags it (it was locked).
  The text still moves only up and down, centred across (owner's choice; the spec's "kéo tự do" was not taken). One
  "Lưu" saves both places, as two api calls as before (no new endpoint).
- **The card is a grid from 576 px:** preview beside the fields, then the button and the scene's picture tools on the
  left beside the "Ảnh chèn" block. The left column stays 220 px (the spec's mock-up had 232) so every card's frame is
  the same size. Below 576 px, one column as before.
- **Turning the inset off asks first only when it has a photo of its own**; turned on again while the card is open, it
  comes back with its size and place (remembered in the card, not stored).
- **Every preview `<video>` in a scene card is muted from the start** (`defaultMuted`, `muted` and, without controls,
  `volume` 0, set by a ref when the element is made). New clips already have `video_sound` false on the server
  (only "Edit từ footage" turns it on), so nothing changes there.

No render change: the MP4 is the same for the same data.
