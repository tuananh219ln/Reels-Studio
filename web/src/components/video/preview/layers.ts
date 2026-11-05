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

/** A layer's name in lists: its text, or its sticker's name. */
export function layerName(layer: SceneLayer): string {
  if (layer.kind === "text") return layer.text.replaceAll("*", "").replace(/\s+/g, " ").trim();
  return STICKERS.find((item) => item.value === layer.sticker)?.label ?? layer.sticker;
}
