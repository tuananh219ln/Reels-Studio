# A scene may read an uploaded MP3, and a group keeps its voice format (2026-11-25)

[Brief](specs/custom-scene-voice-upload/brief.md), asked by the owner.

- **Uploaded narration.** `POST /api/scenes/{id}/voice` (MP3, 20 MB) and MCP `upload_scene_voice` (a direct link)
  make a file the scene's narration; `DELETE` gives the scene back to its voice. The file is signed
  `custom:<sha256>` (cut to the 64 characters of `scenes.voice_signature`): `videos.made_voice_seconds` keeps it
  whatever the voice text or voice, so no voice job or render pays a service for that scene, and the render's
  fingerprint takes its signature, so another file marks the MP4 outdated while service voices keep the fingerprint
  they had. The voice text stays and times the captions.
- **Only the video's maker** sets or removes an uploaded voice (403 otherwise), as the brief asked; other scene edits
  stay open to the team. A clone (`Nhân bản`) does not carry the file: the copy reads its voice text again.
- **The group backup voice cannot stand in for an uploaded file**: nothing is read, so nothing can fail over.
- **"Giọng đọc theo vai"** (`knowledge_topics.voice_format`) is stored, shown on Kho kiến thức and given to assistants
  in `list_topic_groups`; it does not set any scene's voice (scenes have no role). Assigning voices by role is later
  work. Migration 0127 seeds the five groups the team builds today with the formats their build jobs used on
  2026-11-26 (Chi for groups 6, 7 and 10, Roger for FoodDose, OP Chi/Adam and Gemini comments for Topic Threads);
  [2026-11-25-group-voice-standard](2026-11-25-group-voice-standard.md) says how they change once Muse uploads are
  in use.
