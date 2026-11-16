# 2026-11-16 — Gemini TTS voices join ElevenLabs' and VieNeu's, on the Gemini key that makes AI photos

Asked by a member (namtc): Google Cloud Text-to-Speech needs a card even inside its free tier, which the team does
not want to attach, so Gemini TTS (Google AI Studio) is added as a narration service instead. Built the way VieNeu was
(2026-11-07); nothing changes for videos that keep an ElevenLabs or VieNeu voice.

- **A Gemini voice is stored as `gemini:<voice>`** (`gemini:Kore`) in the existing voice ids; no column, option or
  migration. The model is `gemini-3.8-flash-tts` (a constant, part of a narration's signature).
- **No new key and no new env var.** It reads with the Gemini key that already makes AI photos (Cài đặt › Nguồn tư
  liệu, else `IMAGE_GEN_API_KEY`) at `IMAGE_GEN_API_URL`, so the voices are offered whenever that key is set.
- **The 30 prebuilt voices are a fixed list** (no listing call); Google gives each one word of description. They read
  any language, Vietnamese included; the language is detected and the text is read verbatim, no style note is sent.
- **The answer is WAV**, turned into MP3 with FFmpeg; the speed stays FFmpeg's tempo like the other services.
- **The free tier is small and not published** (reports: about 10 requests a minute and 100 a day for this model, not
  raised by paying). Each scene is one request, so a one-minute video of about ten scenes takes about ten of them. A
  per-minute 429 is waited out (3 times, 20 s); the daily one fails the job at once, telling the member to pick
  another voice. The app does not count requests and does not switch voices by itself; both are possible later.
- **Not done:** the `google:` Cloud Text-to-Speech service (PR #260), which needs a billing card.
