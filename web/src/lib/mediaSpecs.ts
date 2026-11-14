import type { MediaItem } from "./api";
import { formatDecimal } from "./api";

/** The pixels of a photo shorter side below this look soft in a 1080×1920 video. */
export const SMALL_SIDE = 720;

/** A file's size the Vietnamese way: "820 KB", "3,4 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${formatDecimal(bytes / (1024 * 1024))} MB`;
}

/** A clip's length: "0:12". */
export function formatClock(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** How a photo's shape sits in a 9:16 video: it fills it, is wider (the sides are cropped) or taller. */
export function shapeOf(item: Pick<MediaItem, "width" | "height">): "tall" | "wide" | "square" | null {
  if (!item.width || !item.height) return null;
  const ratio = item.width / item.height;
  if (ratio < 0.7) return "tall";
  return ratio > 1.15 ? "wide" : "square";
}

/** Whether a photo is small for a vertical video (its shorter side under SMALL_SIDE). */
export function isSmall(item: Pick<MediaItem, "kind" | "width" | "height">): boolean {
  return (
    item.kind === "photo" && Boolean(item.width && item.height) && Math.min(item.width!, item.height!) < SMALL_SIDE
  );
}

/** One line of an item's numbers for its tile: "1080×1920 · 820 KB" for a photo, "0:12 · 8,1 MB" for a clip. */
export function specLine(item: MediaItem): string {
  const parts: string[] = [];
  if (item.kind === "clip") {
    if (item.seconds !== null) parts.push(formatClock(item.seconds));
  } else if (item.width && item.height) {
    parts.push(`${item.width}×${item.height}`);
  }
  if (item.size_bytes !== null) parts.push(formatBytes(item.size_bytes));
  return parts.join(" · ");
}
