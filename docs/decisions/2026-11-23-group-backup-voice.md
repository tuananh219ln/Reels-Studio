# A topic group has a backup voice (2026-11-23)

- A group may name a "Giọng phụ" (`knowledge_topics.voice_backup_id`). When every key of a scene's voice service is
  wrong or spent (`TtsError.key_fault`), `jobs.narrate` reads the scene with the backup voice instead; it may be of
  another service (ElevenLabs main, VieNeu or Gemini backup). A busy or broken service still fails at once.
- The scene's narration signature stays the one of its own voice, so a later render does not pay again.
- ElevenLabs's 402 `paid_plan_required` (a free-plan key asked for a library voice) is the key's plan, not its credit: it
  has its own message and moves on to the next key, as does a 404 `voice_not_found` (a voice lives in one account).
