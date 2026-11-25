# 2026-11-16 — Google Cloud Text-to-Speech voices join ElevenLabs' and VieNeu's; their key is pasted on Cài đặt › Mô hình AI

Asked by a member (namtc): add Google Cloud Text-to-Speech as a third narration service. It is built the way VieNeu
was (2026-11-07); nothing changes for videos that keep an ElevenLabs or VieNeu voice, and ElevenLabs stays the default
voice and the only Speech-to-Text.

- **A Google voice is stored as `google:<voice name>`** (`google:vi-VN-Chirp3-HD-Achernar`) in the existing voice ids
  (`videos.options.voice_id`, a scene's and a topic group's): the prefix sends the narration to Google, so no new
  column, option or migration.
- **An API key, not a service account.** Pasted on Cài đặt › Mô hình AI beside VieNeu's (card "Giọng đọc Google",
  history card 3 of `settings_ai`), stored encrypted (`source_keys`, name `google_tts`, else `GOOGLE_TTS_API_KEY`). A
  service-account JSON would need `google-auth` and token refreshing for nothing the team needs. The key travels in
  the `X-Goog-Api-Key` header, never in the URL.
- **Only `vi-VN` voices are listed**, once a key is set; the narration's language comes from the voice name.
- **The reading speed stays FFmpeg's tempo** on the returned MP3 (2026-11-02), not Google's `speakingRate`, so every
  service sounds the same at a given speed and reuses MP3s the same way. A narration's signature names
  `google-tts-v1` instead of `ELEVENLABS_MODEL`.
- **A text over 5000 bytes is refused before the call** (Google's limit for one request), with a message to split the
  scene, rather than paying for a failed request.
- The web key card is now one component for both services (`VoiceKeyCard`, from `VieneuKeyCard`).
- **"Chỉ dùng mức miễn phí", on by default.** Google bills past each voice kind's monthly free characters and has no
  switch to stop there (a budget only sends alerts, hours late), so the app counts the characters Google read, by kind
  and month, and refuses a narration before the call when it would pass 90 % of its kind's free tier. The margin
  covers the hours by which Vietnam's month starts before Google's (Pacific time) and two jobs counting at once.
  Characters are counted after Google answers (it bills only what it read) and always, so the card shows the month's
  use with the switch off too. A kind with no free tier known to the app is refused while the switch is on. The free
  tiers are written in `google_tts_quota.TIERS` from Google's pricing page of 2026-11; a change there needs a change
  here. Turning the switch off is logged in the Mô hình AI history like the key.
