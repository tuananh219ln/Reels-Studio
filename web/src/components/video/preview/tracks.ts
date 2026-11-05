import type { SceneData } from "@/lib/api";
import { layerName } from "./layers";

/** The tracks under the scenes on the studio's timeline. */
export type Lane = { key: "text" | "layers" | "voice" | "captions" | "music"; name: string };

/** The tracks a member can lock so a stray drag or key changes nothing on them; remembered in their browser. */
export type LockableTrack = "scene" | "text" | "layer";

/**
 * One block on a track: which scene it belongs to (null: the whole video), where it is, what it says. A click plays
 * its scene, or, with `seek`, goes to that second.
 */
export type Span = {
  index: number | null;
  start: number;
  length: number;
  label: string;
  tentative?: boolean;
  seek?: boolean;
};

// The renderer's timing (reels_render.timeline): the narration starts this long into its scene and leaves this much
// of it after it ends. Keep in step with VOICE_LEAD_MS and VOICE_TAIL_MS in VideoPreview.tsx.
const VOICE_LEAD = 0.2;
const VOICE_TAIL = 0.4;

const plain = (text: string) => text.replaceAll("*", "").replace(/\s+/g, " ").trim();

/** The tracks shown for a video: captions only when the render draws them, music only when it has some. */
export function lanesFor(captions: "off" | "phrase" | "word", music: boolean): Lane[] {
  return [
    { key: "text", name: "Chữ" },
    { key: "layers", name: "Lớp" },
    { key: "voice", name: "Giọng" },
    ...(captions !== "off" ? [{ key: "captions" as const, name: "Phụ đề" }] : []),
    ...(music ? [{ key: "music" as const, name: "Nhạc" }] : []),
  ];
}

/** Where a narration sits in its scene: the made MP3's length, else an estimate for the browser's stand-in voice. */
function narration(scene: SceneData, start: number, length: number): Pick<Span, "start" | "length" | "tentative"> {
  const room = Math.max(0.2, length - VOICE_LEAD);
  if (scene.voice_seconds !== null) {
    return { start: start + VOICE_LEAD, length: Math.min(scene.voice_seconds, room) };
  }
  return { start: start + VOICE_LEAD, length: Math.max(0.2, room - VOICE_TAIL), tentative: true };
}

/**
 * The blocks of one track, from the scenes' starts and lengths on the timeline (seconds). The text track has each
 * scene's on-screen text across the scene; the narration and captions tracks have the narration's place (dashed while
 * only the browser's voice reads it, which has no known length); the music track runs the whole video.
 */
export function laneSpans(
  key: Lane["key"],
  scenes: SceneData[],
  starts: number[],
  lengths: number[],
  musicName: string | null,
): Span[] {
  if (key === "music") {
    const total = lengths.reduce((sum, value) => sum + value, 0);
    return total > 0 ? [{ index: null, start: 0, length: total, label: musicName ?? "Nhạc nền" }] : [];
  }
  const spans: Span[] = [];
  scenes.forEach((scene, index) => {
    const start = starts[index];
    const length = lengths[index];
    if (key === "text") {
      const text = plain(scene.text);
      if (text) spans.push({ index, start, length, label: text });
      return;
    }
    if (key === "layers") {
      // Each text or sticker layer for its seconds, cut at its scene's end as the render cuts it.
      for (const layer of scene.layers) {
        if (layer.start >= length) continue;
        const label = `${layer.kind === "text" ? "Chữ" : "Sticker"}: ${layerName(layer)}`;
        spans.push({
          index,
          start: start + layer.start,
          length: Math.min(layer.seconds, length - layer.start),
          label,
          seek: true,
        });
      }
      return;
    }
    if (!scene.spoken_text || (key === "captions" && scene.is_title)) {
      // Captions are never drawn on the title scene, so its first frame stays the thumbnail.
      return;
    }
    const label =
      key === "voice" && scene.voice_seconds === null ? `Giọng tạm: ${scene.spoken_text}` : scene.spoken_text;
    spans.push({ index, label, ...narration(scene, start, length) });
  });
  return spans;
}
