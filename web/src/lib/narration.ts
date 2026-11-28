import type { SceneData, VideoDetail } from "@/lib/api";

/**
 * The scenes that are read aloud, split by where their narration comes from: an MP3 a member uploaded (which stands
 * whatever the voice, speed or text), or the voice service. Both are empty while the video's narration is off.
 */
export function narration(video: VideoDetail): { uploaded: SceneData[]; service: SceneData[] } {
  if (!video.voice_enabled) return { uploaded: [], service: [] };
  const scenes = [...(video.title_scene ? [video.title_scene] : []), ...video.scenes];
  return {
    uploaded: scenes.filter((scene) => scene.voice_custom),
    service: scenes.filter((scene) => !scene.voice_custom && scene.spoken_text !== ""),
  };
}
