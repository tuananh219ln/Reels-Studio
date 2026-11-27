# 2026-11-27 — Phụ đề "Cộng dồn" for PC Shopee (round 2 of the spec)

Round 2 of the spec "Ẩn chữ & Phụ đề Cộng dồn" (Looper, 2026-11-27); round 1 is
[2026-11-27-text-hold.md](2026-11-27-text-hold.md). Built: the captions mode, the three looks ([pc-text-styles](2026-11-27-pc-text-styles.md)), word seconds from ElevenLabs and
the per-scene "Trên / Dưới" button; the compact title and scene text are in [pc-text-tiers](2026-11-27-pc-text-tiers.md).

- **A fourth value of `captions`, `cumulative`** ("Cộng dồn"), offered only for PC Shopee (the web checks the group's name; the
  api accepts the value for any video, as it does the other options). A new PC Shopee video starts with it; turning it off
  on the page gives the scenes' text back and, if no hold was chosen, hides it after 2.5 s (round 1).
- **It replaces the content scenes' text, never the title's or the last scene's** (the call to action), and only in a scene that
  has words to show (a narration, or a clip's own words): a scene with nothing to say keeps its own text instead of going bare.
- **Drawn as pictures, one per step, like the other captions** (`reels_render/cumulative.py`), not as an ASS file: the spec's
  halftone needs pictures anyway and the render already lays caption pictures. Letters are capitals in Bungee (OFL, bundled in
  `fonts/`, all Vietnamese marks checked), white, marked words aqua `#5EF2D0` on their own line, a 6 px `#0B1E2B` outline and a
  cyan glow. A phrase is at most 9 words and 3 lines, ended at punctuation, at a pause over 0.3 s or when full, and a marked run
  is never split. It starts 62% down the frame; its last phrase lasts to the scene's end, so none crosses a cut.
- **Word seconds:** an ElevenLabs narration made while "Cộng dồn" is on is read through `with-timestamps` (same price; the
  characters' seconds become words, divided by the reading speed) and kept per scene (`scenes.voice_words`, migration 0140),
  so the words appear when they are said. Any other narration (another service, an uploaded file, one made before "Cộng
  dồn" was chosen, or a text edited since: the words no longer match) is **estimated** across its length as before. To get
  real seconds for an old narration, make it again ("Tạo giọng thật"); this costs a call, so it is never done silently.
  The spec's ±80 ms is checked by a person on 10 words of a real ElevenLabs narration.
- **Not animated yet:** a word appears at once (the spec's 180 ms pop-in and 150 ms clear are left out: each needs a looped
  input per picture). The numbered circle is in [cumulative-number-circle](2026-11-27-cumulative-number-circle.md). The studio's previews show the first
  phrase whole and still ([tiers](2026-11-27-pc-text-tiers.md)).
- **A render machine on older code refuses** the video (it does not know the value), instead of drawing the old text.
- **A person watches the render** against round 2's checklist, which an agent cannot judge.
