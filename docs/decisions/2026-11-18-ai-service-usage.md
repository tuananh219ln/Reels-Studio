# 2026-11-18 — Cài đặt › Nguồn tư liệu shows how much of each AI service is used

Asked by a member (namtc): show how much each AI key has left and when its plan runs out. Each service tells a
different amount, so each card shows what its service allows, and says when a number is only the app's own count.

- **ElevenLabs is exact:** characters used of the plan, the tier and the reset date, from its subscription endpoint.
  A key with limited permissions needs "User › Read"; the card names the missing permission instead of a number.
- **Cloudflare reads today's neurons** from its GraphQL Analytics API, which needs "Account Analytics › Read" on the
  same token (the image token only needs Workers AI › Read). No second token or env var: without the permission the
  card falls back to the app's own count. The query shape (`aiInferenceAdaptiveGroups.sum.totalNeurons`, filtered by
  `date_geq`) comes from Cloudflare's GraphQL schema as other projects use it; Cloudflare's docs do not show it, so it
  is checked only against the fake service until the real token has the permission.
- **Gemini has no usage API**, so the app counts its own requests: a new table `ai_service_calls`, one row per request
  (photo, photo edit, narration), written before the request like `jobs.image_calls`, kept 35 days. The 2026-11-16
  Gemini TTS decision said the app does not count requests; it now counts them for display only. It still does not
  stop or switch voices on that count.
- **No plan expiry date** is shown for Cloudflare or Gemini: the free tiers do not expire, they reset daily (00:00 UTC
  and midnight Pacific time). ElevenLabs' reset date is the nearest thing to one.
- **Answers are kept 5 minutes** in the process, so opening the page does not call the services each time; "Làm mới"
  asks again.
