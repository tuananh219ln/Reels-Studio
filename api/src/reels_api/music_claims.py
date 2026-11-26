"""Music YouTube claimed (docs/decisions/2026-11-26-youtube-claimed-music.md): a track flagged "Đã bị claim trên
YouTube" goes into no video any more, whichever way music reaches one: "Chọn từ thư viện" (web and MCP `set_audio`)
or a member's default music for new videos. Any video may be uploaded to YouTube later (by hand, or by its Page's
automatic upload), so the refusal holds for every video. A copy a video already holds is not changed."""

from .errors import ApiError
from .models import MusicTrack


def refusal(track: MusicTrack) -> ApiError:
    note = f" ({track.claimed_note})" if track.claimed_note else ""
    return ApiError(
        409,
        "track_claimed",
        f"Bài nhạc “{track.name}” (id {track.id}) đã bị claim trên YouTube{note}. Hãy chọn bài khác.",
    )


def ensure_usable(track: MusicTrack) -> None:
    if track.claimed_on_youtube:
        raise refusal(track)
