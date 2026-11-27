# 2026-11-27 — The scene number stays as an orange circle under "Cộng dồn"

Closes the "numbered circle is not built" point of [cumulative-captions](2026-11-27-cumulative-captions.md).

- "Cộng dồn" replaces a content scene's text, so its leading number ("3.") would vanish. The render keeps it as the orange circle
  of the compact text, centred across just above where the first phrase starts (62% down, or 14% in a "Trên" scene), for the
  first 2.5 s of the scene (`cumulative.NUMBER_SECONDS`), never past the scene's end.
- Only a scene that has "Cộng dồn" steps and a number in its text gets one; the title and the last scene are untouched.
- **A person watches the render** for the circle's place and time, which an agent cannot judge.
