# 2026-11-26 — Music claimed on YouTube is blocked everywhere; YouTube "Riêng tư" is not "đã đăng"

Asked by the owner on 2026-11-26, after video 409 was blocked worldwide on YouTube by a Content ID claim (HAAWK
Publishing, Audiam) on its background music, the library's "Gentle – Peaceful Gentle Music" (track 3), whose licence is
Pixabay's free commercial one. Brief: [docs/specs/platform-health/brief.md](../specs/platform-health/brief.md). The
owner picked all four recommendations of its review ("làm như bạn đề xuất").

1. **A claimed track goes into no video.** `music_tracks.claimed_on_youtube` (with `claimed_at`, `claimed_note`),
   set with "Sửa" on Thư viện nhạc. "Chọn từ thư viện" (web, and MCP `set_audio`, which calls the same route) refuses
   it with the track and its note (409 `track_claimed`), for every video: YouTube auto-upload is switched per Page
   (`fanpages.youtube_auto`), a video has no Page until it is scheduled, and any video can be uploaded by hand, so
   "only videos bound for YouTube" has nothing reliable to test. The track cannot be a member's default music either,
   and a default that was claimed since makes new videos start silent (Cài đặt says so). Videos that already hold a
   copy are not changed: a video keeps only the music's name, not its track, and a clone copies the file, so neither
   can be checked against the flag. Re-rendering posted videos is out of scope.
2. **Seeded by the migration**, guarded so other databases are left alone: track 3 only when its name starts with
   "Gentle", and the claim on video 409 only when it has a YouTube post.
3. **A YouTube private upload is shown as "Riêng tư, chưa công khai"**, amber, not as "✓". It no longer counts in
   "Đã đăng lên X/Y nền tảng" (that number goes down for videos that are only private on YouTube), and its row
   reminds the member to check Content ID in YouTube Studio before making it public: a reminder, not a gate, since the
   app cannot read claims. This changes the publish panel of 2026-11-14 / 2026-11-19, where a private upload counted
   as done.
4. **A claim is noted by hand on the video** as `video_events` rows (`youtube_claim`, `youtube_claim_cleared`, with
   `payload.note`), from "Ghi claim YouTube" on the Đăng bài card or MCP `note_youtube_claim`. While the newest is a
   claim, the YouTube row is "Bị chặn (claim)" and YouTube can be picked again (a clean render may go up). The YouTube
   Data API has no claim state and the Content ID API needs a CMS account, so nothing is read from YouTube, disputed or
   re-uploaded by the app.
