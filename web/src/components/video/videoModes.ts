import type { SceneData, SceneLayer, VideoDetail, VideoMode, VideoOptions } from "@/lib/api";

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
      "cảnh nêu tên món thì thêm ảnh món chồng lên nền, ví dụ “5 món kết hợp với chuối xanh”.",
  },
];

/** A photo layer's frame (reels_render.layers.PHOTO_SHAPES). */
export const PHOTO_SHAPES = [
  { value: "rounded", label: "Bo góc" },
  { value: "circle", label: "Tròn" },
  { value: "square", label: "Vuông" },
  { value: "plain", label: "Giữ nguyên" },
];

/** A photo layer's width (reels_render.layers.SIZES[...].photo): 35%, 48% and 65% of the frame. */
export const PHOTO_SIZES = [
  { value: "small", label: "Nhỏ" },
  { value: "medium", label: "Vừa" },
  { value: "large", label: "Lớn" },
];

/** Where a photo goes at once: its centre in the 1080×1920 frame. Left and right match a new layer's places. */
export const PHOTO_PLACES = [
  { label: "Trái", x: 367, y: 835 },
  { label: "Giữa", x: 540, y: 835 },
  { label: "Phải", x: 713, y: 835 },
  { label: "Dưới", x: 540, y: 1250 },
];

/** "Nghỉ sau lời đọc" (api video_options.VOICE_PAUSES). */
export const VOICE_PAUSES: { value: VideoOptions["voice_pause"]; label: string }[] = [
  { value: 0.4, label: "Ngắn (0,4 giây)" },
  { value: 0.7, label: "Vừa (0,7 giây)" },
  { value: 1, label: "Dài (1 giây)" },
];

export function isBackdrop(video: Pick<VideoDetail, "mode">): boolean {
  return video.mode === "single";
}

export function photoLayer(layers: SceneLayer[]): SceneLayer | undefined {
  return layers.find((layer) => layer.kind === "photo");
}

/**
 * The scenes as the preview plays them. Over a backdrop ("Video xuyên suốt") each content scene shows the title
 * scene's photo, or its clip picked up where the scene before left it (as the render core's backdrop_start does),
 * joined by hard cuts; on a slide video the photo layers, kept for switching back, are left out.
 */
export function previewScenes(video: VideoDetail): SceneData[] {
  const all = [video.title_scene, ...video.scenes].filter((scene): scene is SceneData => scene !== null);
  const title = video.title_scene;
  if (!isBackdrop(video) || title === null) {
    return all.map((scene) => ({ ...scene, layers: scene.layers.filter((layer) => layer.kind !== "photo") }));
  }
  let at = 0;
  return all.map((scene) => {
    const start = at;
    at += scene.fitted_seconds;
    if (scene.is_title) {
      return scene;
    }
    const clip = title.video;
    const picked = clip ? clip.start + start * clip.speed : 0;
    return {
      ...scene,
      video: clip ? { ...clip, start: clip.seconds ? picked % clip.seconds : picked } : null,
      frame_url: title.frame_url,
      preview_url: title.frame_url ?? title.preview_url,
      transition: "cut",
      color: null,
    };
  });
}
