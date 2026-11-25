# 2026-11-24 — The title motion's only sound is a soft ting on each slot

The old title sounds (Vút, a Ting on some dishes, Dâng lên before the "?") were out of step with the slots and sat on
top of the narration. The approved sample has one soft `ding` at the second each slot pops in and nothing else. The
video option `title_sfx` decides: `reveal_ting` (the default) keeps the title scene's sounds in step with the slots
(`title_motion.sync_title_sfx`, run when the title is built, when the title scene's seconds or `title_sfx` change);
`manual` leaves the sounds alone; `off` leaves none. A member adding, changing or removing a sound of that scene
switches the video to `manual`, so a later rebuild never overwrites their edit. `scene_sounds` gains `origin` and
`slot_index` to tell the ting from the member's sounds; the render plays each ting 3 dB under "Nhỏ" (`gain_db`).
Migration 0123 sets `reveal_ting` on draft videos whose title still has the old whoosh + ding + rise pattern; rendered
videos are not touched. The render adds the sound effects together, holds them under -6 dBFS with a limiter (`graph.SFX_LIMIT`) and only
then adds them to the mix. The assistant's `sync_title_sfx` tool re-runs the sync on request.
