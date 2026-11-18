import { formatDateTime } from "@/lib/api";

const ONE_DECIMAL = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const FULL = new Intl.NumberFormat("vi-VN");

/** The full number the Vietnamese way ("24.529.887"), for a tooltip. */
export function formatFull(value: number): string {
  return FULL.format(value);
}

/** A count in short form: under 1.000 as it is, then "1,8 N" (nghìn), "24,5 Tr" (triệu), "1,2 T" (tỷ). */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const units: [number, string][] = [
    [1e9, "T"],
    [1e6, "Tr"],
    [1e3, "N"],
  ];
  for (const [size, unit] of units) {
    if (value >= size) return `${ONE_DECIMAL.format(value / size)} ${unit}`;
  }
  return FULL.format(value);
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "vừa xong", "12 phút trước", "15 giờ trước", "3 ngày trước", then the date (Vietnam time) after a month. */
export function formatAgo(iso: string, now: number): string {
  const away = Math.max(0, now - new Date(iso).getTime());
  if (away < MINUTE) return "vừa xong";
  if (away < HOUR) return `${Math.round(away / MINUTE)} phút trước`;
  if (away < DAY) return `${Math.round(away / HOUR)} giờ trước`;
  if (away < 30 * DAY) return `${Math.round(away / DAY)} ngày trước`;
  return formatDateTime(iso).slice(0, 10);
}

/** A colour for a channel with no avatar yet, the same one every time for the same id. */
export function avatarColor(seed: string): string {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return `hsl(${hash} 45% 40%)`;
}

/** Lower case without accents, so "Phương" is found by "phuong". */
export function plain(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/g, "d")
    .toLowerCase();
}

/** A views threshold as the page writes it: 100000 as "100K", 1000000 as "1M". */
export function thresholdLabel(views: number): string {
  return views >= 1_000_000 ? `${views / 1_000_000}M` : `${views / 1_000}K`;
}
