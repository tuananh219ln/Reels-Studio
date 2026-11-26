import type { VideoDetail } from "@/lib/api";

/** A video Muse wrote with beats is edited by its beats, not scene by scene (docs/decisions/2026-11-26-strategy-beats.md):
 * without beats (every older video, or one Muse has not described yet) the scenes stay the way to edit it. */
export function showsBeats(video: Pick<VideoDetail, "assistant_app" | "beats">): boolean {
  return video.assistant_app === "Muse" && (video.beats?.length ?? 0) > 0;
}
