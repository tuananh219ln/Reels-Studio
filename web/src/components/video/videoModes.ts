import type { GroupVideoMode, SceneData, SceneLayer, VideoDetail, VideoMode, VideoOptions } from "@/lib/api";
import { isHalf } from "./preview/layers";

/** "Kiểu video" (api videos.MODES). */
export const VIDEO_MODES: { value: VideoMode; label: string; hint: string }[] = [
  {
    value: "slides",
    label: "Slide ảnh",
    hint: "Mỗi cảnh một ảnh hoặc clip riêng, ví dụ “5 loại canh sau 50 tuổi”.",
  },
  {
    value: "single",
    label: "Video xuyên suốt",
    hint:
      "Một ảnh hoặc video nền chạy suốt cả video (chọn ở cảnh tiêu đề), các cảnh chỉ đổi chữ và lời đọc; " +
      "cảnh nêu tên món thì có ảnh chèn nửa khung chồng lên nền, ví dụ “5 món kết hợp với chuối xanh”.",
  },
];

/** A topic group's "Kiểu video" (api videos.GROUP_VIDEO_MODES). */
export const GROUP_VIDEO_MODES: { value: GroupVideoMode; label: string }[] = [
  { value: "slides", label: "Slide ảnh" },
  { value: "single", label: "Video xuyên suốt" },
  { value: "alternate", label: "Xen kẽ theo ngày (ngày lẻ: xuyên suốt, ngày chẵn: slide)" },
];

export function videoModeLabel(mode: VideoMode): string {
  return VIDEO_MODES.find((item) => item.value === mode)?.label ?? mode;
}

export function groupVideoModeLabel(mode: GroupVideoMode): string {
  return GROUP_VIDEO_MODES.find((item) => item.value === mode)?.label ?? mode;
}

/** "Nghỉ sau lời đọc" (api video_options.VOICE_PAUSES). */
export const VOICE_PAUSES: { value: VideoOptions["voice_pause"]; label: string }[] = [
  { value: 0.4, label: "Ngắn (0,4 giây)" },
  { value: 0.7, label: "Vừa (0,7 giây)" },
  { value: 1, label: "Dài (1 giây)" },
];

export function isBackdrop(video: Pick<VideoDetail, "mode">): boolean {
  return video.mode === "single";
}

/** The scene's "Ảnh món": a photo layer showing the scene's own photo (not a half-frame photo with its own). */
export function photoLayer(layers: SceneLayer[]): SceneLayer | undefined {
  return layers.find((layer) => layer.kind === "photo" && !isHalf(layer));
}

/**
 * The scenes as the preview plays them. Over a backdrop ("Video xuyên suốt") each content scene shows the title
 * scene's photo, or its clip picked up where the scene before left it, looping over the part from the title scene's
 * start to the clip's end (as the render core's backdrop_start does),
 * joined by hard cuts, so a half-frame photo is placed over the backdrop it will be rendered over; on a slide video
 * the photo layers ("Ảnh món", "Ảnh chèn nửa khung"), kept for switching back, are left out.
 */
export function previewScenes(video: VideoDetail): SceneData[] {
  const all = [video.title_scene, ...video.scenes].filter((scene): scene is SceneData => scene !== null);
  const title = video.title_scene;
  if (!isBackdrop(video) || title === null) {
    return all.map((scene) => ({
      ...scene,
      layers: scene.layers.filter((layer) => layer.kind !== "photo"),
    }));
  }
  let at = 0;
  return all.map((scene) => {
    const start = at;
    at += scene.fitted_seconds;
    if (scene.is_title) {
      return scene;
    }
    const clip = title.video;
    const used = clip?.seconds ? clip.seconds - clip.start : 0;
    const travelled = clip ? start * clip.speed : 0;
    return {
      ...scene,
      video: clip ? { ...clip, start: clip.start + (used > 0 ? travelled % used : travelled) } : null,
      frame_url: title.frame_url,
      preview_url: title.frame_url ?? title.preview_url,
      transition: "cut",
      color: null,
    };
  });
}
