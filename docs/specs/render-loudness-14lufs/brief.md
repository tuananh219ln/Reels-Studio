# Render aims at −14 LUFS (loudness normalisation in the render core)

Written by Muse, 2026-11-26. Code checked on main (HEAD d79713c).

## Context

- The render QC measures EBU R128 loudness against a −14 LUFS target and fails
  when the video is more than 4 LU away (`api/src/reels_api/qc.py:20-21`,
  `TARGET_LUFS = -14.0`, `LUFS_FAIL = 4.0`).
- The 2026-11-07 decision (`docs/decisions.md`, "Every render gets automatic QC"):
  "Making the render itself aim at −14 LUFS (loudness normalisation in the render
  core) is a separate change, to decide once QC shows how far today's renders are
  from it." QC advises and never blocks: a failed check does not fail the render
  or stop posting.
- QC has now shown it: every VieNeu narration renders at −17 to −21 LUFS
  (videos 371–375: −19.7 to −20.6 LUFS), Roger at −19 LUFS — 3–7 LU under target,
  failing or nearly failing on every video. The warning repeats on every video
  and nothing at build time can fix it.
- The render graph applies only linear `volume=` filters
  (`worker/src/reels_render/graph.py:439,453`; `voice_volume` defaults to 100,
  `api/src/reels_api/video_options.py:40`, `worker/src/reels_render/options.py:39`).
  There is no `loudnorm` anywhere in the repo (`git grep loudnorm` is empty).

## Scope

Normalise loudness in the render core (`worker/src/reels_render/graph.py`) so a
finished MP4 lands at −14 LUFS. The coder picks one of the two methods and
records the choice in a decision doc:

(a) Single-pass `loudnorm` (I=−14, TP=−1.5, LRA=11) on the narration chain
    before the mix, or
(b) Measure first (`volumedetect` / two-pass `loudnorm`) and then apply the
    gain — measure on VieNeu, Roger and ElevenLabs voices and pick the method
    that holds up across all three.

Keep true peak at or under −1 dBTP (the QC bar today). Do not change the music
track's level or the ducking behaviour beyond re-mixing at the right level.
QC stays exactly as it is (advisory, measures and reports).

## Out of scope

- Normalising the TTS files themselves — normalise only at render.
- Changing the −14 LUFS target (the platforms' standard).
- Failing a render on a loudness fail (QC stays advisory).

## Acceptance

1. Three test renders (VieNeu, Roger, ElevenLabs narration) → QC loudness
   passes (within ±2 LU), true peak ≤ −1 dBTP.
2. Listening check: no audible pumping or compression artefacts on the voice,
   music ducking still follows the narration.
3. A music-only video (no narration) does not change level unexpectedly.
4. Render time grows by at most 20%.
5. Existing worker tests (`worker/tests/test_graph.py`) and API QC tests
   (`api/tests/test_qc.py`) still pass.

## Risk

Single-pass `loudnorm` changes the voice dynamics slightly (light compression).
A listening check on a real video is mandatory before merge; if single-pass
sounds wrong, use method (b).
