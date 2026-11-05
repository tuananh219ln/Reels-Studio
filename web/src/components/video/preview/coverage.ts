import type { Platform } from "../PlatformFrame";

type Rect = { left: number; top: number; right: number; bottom: number };

/**
 * Where each app draws over the video, in frame pixels (1080 × 1920), as PlatformFrame lays it out: the column of
 * buttons on the right and the channel, caption and sound at the bottom. An estimate of the apps, to warn, not a rule.
 */
const COVERED: Record<Platform, { label: string; rect: Rect }[]> = {
  tiktok: [
    { label: "cột nút bên phải", rect: { left: 975, top: 760, right: 1080, bottom: 1760 } },
    { label: "tên kênh và caption", rect: { left: 0, top: 1580, right: 900, bottom: 1920 } },
  ],
  reels: [
    { label: "cột nút bên phải", rect: { left: 975, top: 940, right: 1080, bottom: 1760 } },
    { label: "tên kênh và caption", rect: { left: 0, top: 1600, right: 900, bottom: 1920 } },
  ],
  shorts: [
    { label: "cột nút bên phải", rect: { left: 975, top: 1080, right: 1080, bottom: 1760 } },
    { label: "tên kênh và caption", rect: { left: 0, top: 1620, right: 900, bottom: 1920 } },
  ],
};

/** What of the app's own drawing the text box at `corner` would sit under; empty when nothing covers it. */
export function coveredBy(
  platform: Platform | "none",
  corner: [number, number],
  size: { width: number; height: number },
): string[] {
  if (platform === "none") return [];
  const box = { left: corner[0], top: corner[1], right: corner[0] + size.width, bottom: corner[1] + size.height };
  return COVERED[platform]
    .filter(
      ({ rect }) => box.left < rect.right && box.right > rect.left && box.top < rect.bottom && box.bottom > rect.top,
    )
    .map(({ label }) => label);
}
