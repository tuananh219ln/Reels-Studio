# Groups 6, 7 and 10 read with VieNeu Huyền My, backup Huyền My too (2026-11-26)

Updates [2026-11-25-group-voice-standard](2026-11-25-group-voice-standard.md) for Già Mà Khỏe (6), Ăn Lành Sống Khỏe
(7) and Nhóm test (10); the other groups are unchanged (FoodDose keeps Roger, Topic Threads its per-role voices).

- The owner set the group voice (`voice_id`) and the backup voice (`voice_backup_id`) of groups 6 and 7 to VieNeu
  Huyền My on Kho kiến thức on 2026-11-26, and keeps Huyền My as the backup: the team may stop using ElevenLabs, so
  ElevenLabs Chi is no longer the backup named in the 2026-11-25 table.
- Their "Giọng đọc theo vai" (`voice_format`), seeded with Chi by migration 0127, now names Huyền My. The owner asked
  for this as a migration (0128) rather than an edit on Kho kiến thức, reversing that decision's "no migration" for
  these three groups only. 0128 changes a group only while it still holds 0127's seed, so an edit made by hand stays.
- Nhóm test's note says the clone rule of 2026-11-26: keep the source video's voice, and switch to VieNeu Huyền My only
  when that voice is off standard. Its `voice_id` stays as members set it.
