/**
 * The studio's per-scene effects, the render's named presets (worker/src/reels_render/effects.py; keep the two lists
 * in step), with what the browser preview draws for each: a CSS animation for the transition into a scene
 * (editor.css, `preview-t-<name>`) and a CSS filter close to each colour preset. CSS has no curves or per-tone colour
 * balance, so the colours are near the MP4's, not the same; the render is what counts.
 *
 * The colour approximations follow AIEV's (https://github.com/notivn/AIEVv2, engines/remotion/src/color.ts,
 * PRESET_APPROX and gradeAdjustCss), MIT licence, Copyright (c) 2026 noti.vn; the full notice is in effects.py.
 */

export type SceneTransition =
  | "fade"
  | "cut"
  | "slide"
  | "slide_up"
  | "wipe"
  | "zoom"
  | "circle"
  | "black"
  | "flash"
  | "dissolve"
  | "blur"
  | "pixel";

export const SCENE_TRANSITIONS: { value: SceneTransition; label: string }[] = [
  { value: "fade", label: "Mờ dần" },
  { value: "cut", label: "Cắt thẳng" },
  { value: "slide", label: "Trượt sang trái" },
  { value: "slide_up", label: "Trượt lên" },
  { value: "wipe", label: "Quét ngang" },
  { value: "zoom", label: "Phóng vào" },
  { value: "circle", label: "Mở vòng tròn" },
  { value: "black", label: "Qua màu đen" },
  { value: "flash", label: "Chớp trắng" },
  { value: "dissolve", label: "Hoà tan" },
  { value: "blur", label: "Nhoè ngang" },
  { value: "pixel", label: "Vỡ điểm ảnh" },
];

export const COLOR_PRESETS: { value: string; label: string; css: string }[] = [
  { value: "natural", label: "Tự nhiên", css: "contrast(1.06) saturate(1.12)" },
  { value: "bright", label: "Tươi sáng", css: "brightness(1.03) contrast(1.08) saturate(1.33)" },
  { value: "vivid", label: "Rực rỡ", css: "contrast(1.12) saturate(1.5)" },
  { value: "cinematic", label: "Điện ảnh", css: "contrast(1.08) saturate(1.05) sepia(0.04)" },
  { value: "teal_orange", label: "Xanh cam", css: "contrast(1.1) saturate(1.15) sepia(0.07)" },
  { value: "vintage", label: "Phim cũ", css: "contrast(0.9) saturate(0.85) sepia(0.09)" },
  { value: "matte", label: "Phim mờ", css: "brightness(1.01) contrast(0.97) saturate(0.9)" },
  { value: "golden", label: "Nắng vàng", css: "brightness(1.02) saturate(1.1) sepia(0.31)" },
  { value: "warm", label: "Ấm", css: "saturate(1.08) sepia(0.23)" },
  { value: "cool", label: "Lạnh", css: "saturate(1.05) hue-rotate(7deg)" },
  { value: "night", label: "Đêm xanh", css: "brightness(0.97) contrast(1.1) saturate(0.95) hue-rotate(10deg)" },
  { value: "moody", label: "Trầm", css: "brightness(0.96) contrast(1.18) saturate(0.8) hue-rotate(2deg)" },
  { value: "pastel", label: "Pastel", css: "brightness(1.05) contrast(0.92) saturate(0.85)" },
  { value: "mono", label: "Đen trắng", css: "contrast(1.15) saturate(0)" },
];

/** The clip speeds offered in the studio (the api takes any from 0.5 to 2). */
export const CLIP_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/** The CSS filter close to a colour preset; undefined for the picture as shot. */
export function colorCss(color: string | null | undefined): string | undefined {
  return COLOR_PRESETS.find((item) => item.value === color)?.css;
}

export function transitionLabel(value: string): string {
  return SCENE_TRANSITIONS.find((item) => item.value === value)?.label ?? value;
}
