/**
 * The sound effects and music levels, as the render core names them (worker/src/reels_render/sounds.py; keep the
 * labels and levels in step). The sounds themselves come from the api, made by the same FFmpeg filters.
 */

export const SOUNDS: { value: string; label: string; seconds: number }[] = [
  { value: "whoosh", label: "Vút", seconds: 0.6 },
  { value: "swoosh", label: "Lướt nhanh", seconds: 0.35 },
  { value: "ding", label: "Ting", seconds: 0.9 },
  { value: "pop", label: "Bụp", seconds: 0.15 },
  { value: "click", label: "Tách", seconds: 0.06 },
  { value: "boom", label: "Bùm", seconds: 1.2 },
  { value: "rise", label: "Dâng lên", seconds: 1.2 },
  { value: "success", label: "Hoàn thành", seconds: 0.8 },
  { value: "wrong", label: "Sai rồi", seconds: 0.6 },
  { value: "coin", label: "Tiền về", seconds: 0.7 },
  { value: "heartbeat", label: "Nhịp tim", seconds: 0.7 },
];

export const SOUND_VOLUMES = [
  { value: "soft", label: "Nhỏ", gain: 0.5 },
  { value: "normal", label: "Vừa", gain: 1 },
  { value: "loud", label: "To", gain: 1.6 },
];

/** A scene's own music level, multiplying the video's; "video" stands for none (the video's level). */
export const MUSIC_LEVELS = [
  { value: "video", label: "Theo video", gain: 1 },
  { value: "off", label: "Tắt nhạc", gain: 0 },
  { value: "low", label: "Nhạc nhỏ", gain: 0.4 },
  { value: "high", label: "Nhạc to", gain: 1.6 },
];

export const soundUrl = (name: string) => `/api/sounds/library/${name}.mp3`;
export const soundLabel = (name: string) => SOUNDS.find((item) => item.value === name)?.label ?? name;
export const soundSeconds = (name: string) => SOUNDS.find((item) => item.value === name)?.seconds ?? 0.5;
export const soundGain = (volume: string) => SOUND_VOLUMES.find((item) => item.value === volume)?.gain ?? 1;
export const musicGain = (level: string | null) => MUSIC_LEVELS.find((item) => item.value === level)?.gain ?? 1;
