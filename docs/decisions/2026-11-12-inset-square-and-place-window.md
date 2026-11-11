# 2026-11-12 — "Ảnh chèn" is a rounded square with a photo of its own, placed in one window with the text

Asked by tuananh219ln from a spec ("Spec: Ảnh chèn và vị trí chữ trong cảnh", with a mock-up), owner's answers to the
open points in the same session. It changes what PR #197 (2026-11-11) shipped and part of 2026-11-09:

- **A square narrower than the frame**, `height` percent of the frame's height on each side (30–45%, 32% for a new
  one: 614 px; 45% is 864 px, still narrower than 1080), centred across, **rounded corners, no border**. This replaces
  #197's edge-to-edge strip with faded edges (owner's choice among 1:1, the old 9:8 and 4:5; and among a white edge,
  no edge, or keeping the fade). `height` keeps its column and range; it now means the square's side.
- **A new one is flush with the bottom edge** at 32% (was flush with the top at 38%), whether turned on in the card,
  added by the assistant or given by a script. With an inset not flush with the top, an unplaced text still goes to
  the top (`opposite_the_inset`, unchanged).
- **The inset gets a photo of its own from the card again**: Tải lên, Kho, Tìm and AI in the "Ảnh chèn" block, kept
  apart from the scene's picture tools. This reverses the part of 2026-11-09 ("'Ảnh chèn nửa khung' only on a 'Video
  xuyên suốt', and it is the scene's dish photo") that took the web's own upload and library buttons away (owner's
  choice). Turning the inset on still shows the scene's photo until one is chosen, so a script's inset works as before;
  "AI" lets the inset's own copy go and makes the scene's photo with the scene's AI job (no new job kind). A new photo
  replaces the inset's own in place (same layer, place and size; the older copy deleted) instead of being refused.
- **No Trên / Giữa / Dưới buttons.** The text and the inset are each dragged up and down in one window with two tabs
  (Chữ, Ảnh chèn), the other one dimmed and locked; arrow keys move by 10 px. "Chỉnh vị trí chữ" is on every content
  scene of a "Video xuyên suốt", inset or not.
- **Spec's open questions:** the inset still goes flush with the top and bottom edges, with no extra margin for the
  platforms' buttons; the text keeps the title window's limits (the safe zone, y 220–1440), centred across.
- Rejected: storing a free `x` or a new field; the spec asked for neither, and the existing `y`, `height`,
  `text_position` and `placed_at` carry everything.

The render changes (the square, its corners, `InsetInput.left`), so a person watches a sample MP4 (a 4:3 and a 9:16
photo, flush with the top and with the bottom, 30% and 45%, over a backdrop clip) before this is called done. MP4s
rendered before keep their look until they are rendered again.
