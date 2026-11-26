# Muse uploads and VieNeu become the groups' standard voices (2026-11-25)

Takes effect once per-scene voice upload (P3, `source: custom`) is on `main`; until then each group keeps the voices
it is built with today (ElevenLabs Chi; Roger for FoodDose).

- "Muse" here is the assistant connected over MCP, not a TTS service: it makes a scene's narration and uploads it as
  the scene's own file. VieNeu Huyền My is the voice the app reads with when a scene has no uploaded file.
- Standard per topic group:

  | Group | Voice when built | Group voice (`voice_id`) | Group backup (`voice_backup_id`) |
  | --- | --- | --- | --- |
  | Ăn Lành Sống Khỏe (7) | Muse upload, else VieNeu Huyền My | VieNeu Huyền My | ElevenLabs Chi |
  | Già Mà Khỏe (6) | Muse upload, else VieNeu Huyền My | VieNeu Huyền My | ElevenLabs Chi |
  | Nhóm test (10) | as group 7 | VieNeu Huyền My | none |
  | Topic Threads (9) | Muse upload per role, VieNeu for the other roles | none (set per scene) | VieNeu |
  | FoodDose (12) | ElevenLabs Roger, until its timed motion is checked against another voice | none | none |

- Group 6 now matches the 2026-11-08 entry (Già Mà Khỏe reads with VieNeu Huyền My); group 7 moves from ElevenLabs
  Chi to VieNeu Huyền My.
- One voice source per video, except Topic Threads, whose roles are meant to differ: a Muse file beside Huyền My in
  one video sounds uneven.
- An uploaded file calls no TTS service, so the group backup voice cannot stand in for it: a missing or broken file is
  uploaded again. The backup only covers scenes read by a service
  ([2026-11-23-group-backup-voice](2026-11-23-group-backup-voice.md)).
- The `[excited]` tag works only with ElevenLabs `eleven_v3`, and the "at most 2 Gemini scenes" limit was a build
  convention, not a code rule; neither applies to Muse or VieNeu narration.
- The groups' settings on Kho kiến thức are changed by a member by hand when this takes effect; no migration.
