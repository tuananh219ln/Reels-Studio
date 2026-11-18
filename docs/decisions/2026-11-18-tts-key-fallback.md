# 2026-11-18 — Narration moves to the next team key when a key is wrong or out of quota

Asked by the owner (namtc). Builds on 2026-11-16 "gemini-tts", which failed a render at once when the Gemini key's
day ran out: now the next key is tried first. The app still never switches the **voice** by itself.

- **Team keys only.** A first draft added each member's own keys ("Key API của tôi"); the owner dropped them before
  merge: every key is the team's, under the main key on Cài đặt › AI và nguồn tư liệu › Giọng đọc.
- **Several keys per narration service.** ElevenLabs, Gemini and VieNeu keep their main key where it was
  (`app_settings.source_keys`, so nothing is migrated and nobody pastes again) and get "Key dự phòng" under it
  (`api_keys`, up to 10 per service), ordered with up/down buttons (not drag and drop: simpler, and steady in E2E).
  To make a backup the main one, paste it as the main key.
- **Order tried:** the main key (or the `.env` key when none is saved, as before), the backups, then the `.env` key
  if not tried yet.
- **A key at fault moves on**: wrong or revoked (401, Gemini's API_KEY_INVALID), not allowed (403), or out of quota
  (Gemini's daily 429, ElevenLabs' 402 or "quota" — it answers a spent plan with HTTP 401 `quota_exceeded` — and
  VieNeu's trial daily 429 or 402/credit). The owner asked for wrong keys to move on too, so a broken key no longer
  stops the render; instead it is **shown at once on its own row** (reason and Vietnam time) and cleared the next time
  it reads. Not the key's fault, so no switch and no mark: Gemini's per-minute 429 (still waited out on the same
  key), a server or network error, a missing voice or model.
- **A failed key is skipped for the rest of the job**, not between jobs: the next job starts from the top (a refused
  request answers fast and costs nothing), so a topped-up key is used again without anyone clearing it.
- **Every key failing:** the job fails saying how many keys were tried and where to see each key's error. With a
  single key the reason is that key's own, as before.
- **One key for everything else:** AI photos, photo edits and a sample video's words keep using the main key alone;
  the voice picker lists each service's voices with the first key that answers, without merging lists.
- Each switch is logged (service, the key's name and last four characters, never the key), and backup keys added,
  renamed, moved or removed are in the settings history the same way.
