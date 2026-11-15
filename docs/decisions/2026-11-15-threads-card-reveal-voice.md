# 2026-11-15: Cards, "Hiện dần", per-scene voice and reading speed up to 1.5

For the two comment-reading pages copying the 3AM Diary format (a white Threads screenshot over a moving background,
read fast, sometimes a second voice for a set-apart ending).

- **Reading speed goes up to 1.5** (was 1.3, "Reading speed is a slider from 0.7× to 1.3×", 2026-11-02, owner's
  request in the brief). Same FFmpeg `atempo`, same 0.05 step; values already saved are untouched.
- **A scene may have its own voice** (`scenes.voice_id`, null: the video's). Every step that makes, signs or checks a
  scene's narration asks `video_options.scene_voice`, so a scene with its own voice is not read again on every render
  (paying ElevenLabs twice). Duplicates keep it, splits copy it; templates do not carry it (a voice belongs to the
  content, not to the edit). Scenes have no edit history, so it is not logged there.
- **"Thẻ" is a new photo layer style, on slide videos too.** Neither existing photo layer fits a tall screenshot: a
  slide scene's photo fills the frame, and "Ảnh chèn" (backdrops only, 2026-11-09) is a square cut to fill. A card is
  kept whole, hung from its top edge, under the text; it does not change the "Ảnh chèn only on a backdrop" decision.
- **"Hiện dần" stays inside one scene**, the card laid once per part with the rows below cleared, timed by the share
  of words before each part over the narration's length. The brief suggested one scene per part ("cảnh cộng dồn") for
  exact timings; one scene was chosen instead because the background then runs on without chaining clip starts across
  scenes and the narration is one natural read. The cost is timing by estimate; ElevenLabs timestamps can replace the
  estimate later without changing the data.
- **A different background per card** needs no new code: a clip per scene with the `cut` transition, its own sound off,
  "Lặp clip" for a short clip (documented in muse-footage.md).
- Threads screenshots imported by link are left for a later change: it needs a paid screenshot service the owner has
  to choose first. Card pictures come from the library or a photo link. Names and avatars on the cards are kept as
  they are (owner, 2026-11-15).
