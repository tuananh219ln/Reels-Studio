# Brief: Custom narration audio per scene (upload voice MP3)

- Date: 2026-11-26. Asked by the operator; written by Muse.
- Base: `origin/main` HEAD `2742dbf` — every file:line below was verified against that HEAD on 2026-11-26. Branch new work from `main`, never commit to `main`. PR description in Vietnamese (fill the PR template).
- Use case: the operator generates narration MP3s outside the tool (e.g. an AI assistant's own TTS voices, or a human-recorded voice) and wants them used as a scene's narration, keeping captions, automatic scene length, and the whole render / schedule / auto-post pipeline.

> Kept as written, as history (docs/specs is not kept up to date). What was built and where it differs is in
> [decisions/2026-11-25-custom-scene-voice.md](../../decisions/2026-11-25-custom-scene-voice.md).

## Problem (verified)

Narration today is generated server-side only. `make_voices()` (`api/src/reels_api/jobs.py:691`) calls `tts.synthesize()` (`api/src/reels_api/tts.py:162`) for ElevenLabs / VieNeu / Gemini / Google, stores the MP3 at `videos/{id}/voice-{scene.id}-{hex}.mp3`, and render copies that stored file (`jobs.py:874`). There is no endpoint to upload or replace a narration MP3: `GET /scenes/{scene_id}/voice.mp3` (`api/src/reels_api/routes_videos.py:2451`) is listen-only, and `POST /videos/{video_id}/voices` (`routes_videos.py:690`) only triggers the TTS job.

## Goal

Upload a custom MP3 as one scene's narration. The render must use it, re-uploading must invalidate the MP4, captions must keep working, and the scene must auto-fit to the custom audio length. No change to existing TTS flows.

## Design

### 1. New endpoint `POST /api/scenes/{scene_id}/voice`

Mirror `upload_music` (`api/src/reels_api/routes_videos.py:969-986`):

- Multipart MP3, max 20 MB (same cap pattern as music: `read_limited(file, MAX_MUSIC_BYTES, ...)` — define `MAX_VOICE_BYTES` or reuse; keep 20 MB). `check_mp3(data)` failure → 415 with a distinct code, e.g. `invalid_voice`.
- Load the scene with the existing `_scene(db, scene_id)` helper (used by `GET voice.mp3`); resolve its video; `lock_video(db, video.id)`; `ensure_unlocked(db, video)`; `ensure_owner(video.created_by_id, me.user_id, "video này")` (same pattern as `routes_videos.py:646`).
- Probe duration with ffprobe (`audio_seconds`, exactly as `make_voices` does at `jobs.py:717-721`); if unreadable, reject the upload as an API error instead of storing a broken file.
- Store with `new_key(video.id, f"voice-{scene.id}", "mp3")` (same key shape as `make_voices`, `jobs.py:714`) and `storage.save_bytes(key, data)`; delete the old key.
- Set `scene.voice_key = key`, `scene.voice_seconds = seconds`, `scene.voice_signature = f"custom:{sha256_hex(data)}"`. If `scene.seconds_auto`, set `scene.seconds = auto_seconds(seconds, voice_pause(video))` (same as `make_voices`, `jobs.py:727-728`).
- Return the saved video payload (`_saved(db, video)`), same as `upload_music`.
- No migration: `Scene.voice_key` (String 200), `voice_signature` (String 64), `voice_seconds` (Float) already exist (`api/src/reels_api/models.py:465-469`).

### 2. Skip custom voices in `make_voices` (`api/src/reels_api/jobs.py:691-730`)

- Current skip (line 698): `made_voice_seconds(video, scene) is not None and storage.exists(scene.voice_key)`.
- `made_voice_seconds` (`api/src/reels_api/videos.py:351-356`) returns `None` when `scene.voice_signature != voice_signature(text, *_voice(video, scene))`. A `custom:<hash>` signature never matches a TTS signature, so without a change the next render job would regenerate (and bill) TTS over the custom file.
- Change: treat a signature starting with `"custom:"` as valid — return `scene.voice_seconds` from `made_voice_seconds` (preferred, single place), keeping the `storage.exists(scene.voice_key)` guard. `POST /videos/{video_id}/voices` needs no change; it flows through `make_voices`.

### 3. Fingerprint: re-upload must invalidate the MP4

- `render_signature` (`api/src/reels_api/videos.py:581-640`) builds `voices` at line 631 as `voice_signature(spoken(video, scene), *_voice(video, scene)) if spoken(video, scene) else None`, joined into the fingerprint only `if any(voices)`.
- Change: when `scene.voice_signature` starts with `"custom:"`, use `scene.voice_signature` itself in the `voices` list instead of the TTS-derived signature. Uploading a different MP3 with the same text then changes the fingerprint, so `rendered_signature != render_signature(...)` (`routes_videos.py:861`) flags the MP4 outdated and a re-render picks up the new audio.
- Do not change the fingerprint shape for TTS voices: existing MP4s must stay current (no mass "outdated" flags).

### 4. Captions and scene length keep working — no render changes

- Render copies the stored voice file directly: `data["voice"] = storage.copy_to(scene.voice_key, ...)` (`jobs.py:874`); the worker probes its length (`worker/src/reels_render/render.py:400-408`) and fits the scene (`worker/src/reels_render/timeline.py:28`, `fit_seconds = max(seconds, 0.2 + voice + 0.4)`).
- Captions are planned from `voice_text` plus the probed voice length (`render.py:158-160`: only when `spoken[index]` is set and `scene.voice_text` is non-empty). The upload must NOT change `scene.voice_text` — captions stay correct. Verify in tests.
- `GET /scenes/{scene_id}/voice.mp3` (`routes_videos.py:2451`) already serves `scene.voice_key` — no change; it becomes the preview player for the custom file too.

### 5. Delete custom voice

- `DELETE /api/scenes/{scene_id}/voice`: same locking / ownership checks; clear `voice_key`, `voice_signature`, `voice_seconds` and delete the storage file. The next voices job regenerates TTS normally. Return the saved video payload.

### 6. MCP tool + web UI

- MCP: new tool `upload_scene_voice`, modelled on `add_music_from_link` (`mcp_server.py:2234`). MCP has no multipart file upload, so the tool takes `scene_id` plus a direct-download URL (a Drive `uc?export=download&id=` link works — `_RedirectHandler` follows redirects, `remote_media.py:106-127`; a `/file/d/.../view` link does NOT, it downloads HTML and fails `check_mp3`). Download server-side, validate with `check_mp3`, then store exactly as the endpoint does. The tool name must also be added to the client allowlist (`custom.reels-studio` client `ALLOWED_TOOLS`) — that file lives outside this repo; the operator updates it, the coder only adds the server tool.
- Web UI: an upload button in `VoiceText.tsx`, next to the existing preview that uses `GET voice.mp3`. Show a "custom voice" badge with file name and duration, plus Replace and Remove actions calling the new endpoints. No other UI changes.

### 7. Per-group voice format settings (new — operator asked 2026-11-26)

**Why.** Each group has its own voice format (one group = one voice; Threads = many voices by role). Today that format lives only in the build jobs' instructions, not in the tool — a builder can pick the wrong voice. The group already stores a default voice (`KnowledgeTopic.voice_id`, `models.py:171-173`) and a backup (`voice_backup_id`, `models.py:174-176`, fallback in `jobs.py:739-745`), but there is no stored format for multi-voice roles, no source field (provider TTS vs uploaded file), and no per-role rules.

**Change.**

- New JSONB column `KnowledgeTopic.voice_format` (default `{}`). Unlike parts 1–5, this part DOES need a migration. Schema:
  - `mode`: `"single"` | `"multi"`.
  - `roles`: array of `{ "role": "all" | "op" | "comment" | "cta", "voice": "<ElevenLabs id | vieneu:<name> | google:<name> | custom>", "source": "provider" | "custom", "volume": 100 }`. `mode: "single"` uses one role `"all"`. `mode: "multi"` uses a `comment` role with a rotation list `"voices": [...]`.
  - `rules`: `{ "max_gemini_scenes": 2, "excited_tag": "elevenlabs-only, max 1/video" }` (Threads today; other groups omit).
- The group-update endpoint already accepts `voice_id` / `voice_backup_id` (`routes_videos.py:2521-2522, 2810-2817`); extend the same schema with `voice_format` (validate shape, reject unknown roles/sources). The group settings UI gets a "Giọng đọc theo vai" section editing it.
- MCP: include `voice_format` in the topic read response (and `list_topic_groups`) so builders read the format from the tool instead of job text. No new MCP write tool — the operator edits it in the web UI.
- `voice_id` stays the single default voice (new videos start with it); `voice_backup_id` stays the fallback when a voice cannot be read. `voice_format` does not duplicate them — it only adds roles + source + rules. A role with `source: "custom"` means the scene's narration is an uploaded file (parts 1–5); the tool never synthesises it.
- Enforcement scope: this part STORES the format and exposes it; it does not auto-assign roles to scenes (scenes have no role field; `Scene.voice_id`, `models.py:457-459`, is still set per scene by the maker). The builder (agent or human) reads `voice_format` and sets `scene.voice_id` / uploads accordingly. Auto-assignment is a follow-up, out of scope here.

**Seed values (operator's current formats — live group settings verified in the web tool 2026-11-26 00:32; exact VieNeu ids from Settings → Voices):**

- Ăn Lành (7): single — Chi `5yEPTrA0uAhZsBEhHjfi` (group `voice_id`, verified live). Backup = VieNeu Huyền My (`vieneu:Huyền My`), set in group settings 2026-11-26 00:54 (verified by reload).
- Già (6): single — Chi (group `voice_id`, verified live). Backup = VieNeu Huyền My (`vieneu:Huyền My`), set in group settings 2026-11-26 00:53 (verified by reload).
- Ăn Ngon clone (10): single — Chi; backup none (never VieNeu). Group `voice_id` EMPTY (verified live) — Chi is set per video by the build.
- Threads (9): multi — OP by vibe (V1–V3 Chi, V4–V6 Adam `pNInz6obpgDQGcFmaJgB`); comments rotate voices, max 2 Gemini scenes/video; `[excited]` ElevenLabs-only, 1/video. Group `voice_id` EMPTY (verified live) — voices are set per scene by the build.
- FoodDose (12): single — Roger `CwhRBWXzGAHq8TQ4Fs17`, volume 100. Group `voice_id` EMPTY (verified live) — Roger is set per video by the build.

## Acceptance criteria

1. Upload a valid MP3 to a scene → `GET voice.mp3` plays it; rendering the video uses it as narration (verify by listening to the MP4, and by confirming the render job copies `voice_key`).
2. Re-uploading a different MP3 with the same `voice_text` marks the MP4 outdated (`rendered_signature` mismatch) and a re-render picks up the new audio.
3. `POST /videos/{video_id}/voices` (and the next render job) does NOT regenerate TTS for a scene with a custom voice; no TTS cost is incurred for it.
4. Captions ("phrase") still appear, timed to the custom audio length; `seconds_auto` scenes resize to the custom audio length.
5. Deleting the custom voice restores normal TTS generation on the next voices job.
6. Errors: non-MP3 → 415; over 20 MB → rejected with the size message; non-owner → 403; locked / rendering video → the same lock error as music upload.
7. Existing TTS flows unchanged: videos without custom voices keep byte-identical fingerprints (no mass "outdated" flags).
8. Voice format (part 7): group settings save a `voice_format`; the topic read (API + MCP) returns it; a builder reading only the tool gets the right voice per role for all 5 seeded groups; existing `voice_id` / `voice_backup_id` behaviour unchanged.

## Out of scope

- A new TTS provider (e.g. calling an external TTS API from the server) — explicitly not this; upload only.
- Bulk upload, music changes, caption logic changes.
- Changing `voice_text` semantics or the `spoken()` fallback (`videos.py:304`).

## Tests

Repo "Done" = lint + typecheck pass, tests for changed behaviour exist and pass, docs in `docs/` updated in the same PR.

- API tests: upload happy path (key / signature / seconds set, old file deleted), non-MP3 → 415, oversize, non-owner → 403, locked video, delete restores TTS.
- Unit tests: `made_voice_seconds` returns seconds for `custom:` signatures; `render_signature` changes on re-upload and is unchanged for TTS voices.
- One end-to-end render test with a fixture MP3: captions present, scene seconds match the fixture length.
- Run: `cd web && npm run format && npm run lint && npm run typecheck`, plus the api tests.
