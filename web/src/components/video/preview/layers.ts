/**
 * The layers' named presets, as the render core names them (worker/src/reels_render/layers.py; keep the labels in
 * step). Pictures come from the api, drawn by the render core, so only the entrance is played here.
 */

import type { SceneLayer } from "@/lib/api";

export const STICKERS: { value: string; label: string }[] = [
  { value: "arrow_down", label: "Mũi tên xuống" },
  { value: "arrow_right", label: "Mũi tên phải" },
  { value: "ring", label: "Khoanh tròn" },
  { value: "star", label: "Ngôi sao" },
  { value: "heart", label: "Trái tim" },
  { value: "check", label: "Dấu tích" },
  { value: "cross", label: "Dấu X" },
  { value: "new", label: "Nhãn MỚI" },
  { value: "hot", label: "Nhãn HOT" },
  { value: "sale", label: "Nhãn SALE" },
];

export const TEXT_STYLES = [
  { value: "outline", label: "Chữ viền" },
  { value: "yellow", label: "Hộp vàng" },
  { value: "dark", label: "Hộp đen" },
  { value: "white", label: "Hộp trắng" },
  { value: "red", label: "Hộp đỏ" },
];

export const SIZES = [
  { value: "small", label: "Nhỏ" },
  { value: "medium", label: "Vừa" },
  { value: "large", label: "Lớn" },
];

export const ANIMATIONS = [
  { value: "none", label: "Hiện ngay" },
  { value: "fade", label: "Mờ dần" },
  { value: "slide_up", label: "Trượt lên" },
  { value: "slide_left", label: "Trượt từ trái" },
];

/** The render core's entrance length (layers.ANIMATION_SECONDS). */
export const ENTRANCE_SECONDS = 0.3;

export const FRAME_WIDTH = 1080;
export const FRAME_HEIGHT = 1920;

/** Where the layer's picture goes: centred on its place, never past the frame's edges (layers.layer_corner). */
export function layerCorner(width: number, height: number, layer: Pick<SceneLayer, "x" | "y">): [number, number] {
  const left = Math.min(Math.max(layer.x - Math.floor(width / 2), 0), Math.max(FRAME_WIDTH - width, 0));
  const top = Math.min(Math.max(layer.y - Math.floor(height / 2), 0), Math.max(FRAME_HEIGHT - height, 0));
  return [left, top];
}

/**
 * "Ảnh chèn" (layers.HALF): a photo layer with a photo of its own, as wide as the frame (no edge, square corners),
 * 38% of the frame tall (30–45%), that moves only up and down, flush with the top edge, the middle or the bottom edge;
 * the server keeps it there too. Its edge towards the picture behind it fades out, drawn by the api.
 */
export const HALF = "half";
export const HALF_X = FRAME_WIDTH / 2;
export const HALF_HEIGHT_DEFAULT = 38;
export const HALF_HEIGHT_MIN = 30;
export const HALF_HEIGHT_MAX = 45;
/** Where a dragged inset photo snaps to when it comes this close: flush with the top, the middle, flush with the bottom. */
const HALF_SNAP = 40;

/** Its height in frame pixels (layers.half_height): 38% is 730. */
export function halfHeight(percent: number = HALF_HEIGHT_DEFAULT): number {
  return Math.round((FRAME_HEIGHT * Math.min(Math.max(percent, HALF_HEIGHT_MIN), HALF_HEIGHT_MAX)) / 100);
}

/** The three places an inset photo goes, as the centre `y` that puts it flush with an edge (or in the middle). */
export function halfPlaces(percent: number = HALF_HEIGHT_DEFAULT): { value: string; label: string; y: number }[] {
  const tall = halfHeight(percent);
  return [
    { value: "top", label: "Trên", y: Math.floor(tall / 2) },
    { value: "middle", label: "Giữa", y: FRAME_HEIGHT / 2 },
    { value: "bottom", label: "Dưới", y: FRAME_HEIGHT - Math.floor(tall / 2) },
  ];
}

export function isHalf(layer: Pick<SceneLayer, "kind" | "style">): boolean {
  return layer.kind === "photo" && layer.style === HALF;
}

/** An inset photo's centre down the frame: kept inside it, and snapped to a nearby edge or the middle. */
export function halfY(y: number, percent: number = HALF_HEIGHT_DEFAULT): number {
  const places = halfPlaces(percent);
  const kept = Math.round(Math.min(Math.max(y, places[0].y), places[2].y));
  return places.find((place) => Math.abs(place.y - kept) <= HALF_SNAP)?.y ?? kept;
}

/** A layer's name in lists: its text, its sticker's name, "Ảnh chèn" or "Ảnh món". */
export function layerName(layer: SceneLayer): string {
  if (layer.kind === "text") return layer.text.replaceAll("*", "").replace(/\s+/g, " ").trim();
  if (isHalf(layer)) return "Ảnh chèn";
  if (layer.kind === "photo") return "Ảnh món";
  return STICKERS.find((item) => item.value === layer.sticker)?.label ?? layer.sticker;
}
