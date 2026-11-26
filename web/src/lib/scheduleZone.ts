/** The zone a posting schedule is written in (api schedule_tz.py): Vietnam, or one of three US zones. */
export const VN_ZONE = "Asia/Ho_Chi_Minh";
export const US_ZONES = [
  { value: "America/New_York", label: "ET (New York)" },
  { value: "America/Chicago", label: "CT (Chicago)" },
  { value: "America/Los_Angeles", label: "PT (Los Angeles)" },
] as const;
export const DEFAULT_US_ZONE = US_ZONES[0].value;

export function isUs(zone: string): boolean {
  return zone !== VN_ZONE;
}

/** "giờ Việt Nam" / "giờ Mỹ ET": what the member reads next to a time. */
export function zoneName(zone: string): string {
  if (zone === VN_ZONE) return "giờ Việt Nam";
  const us = US_ZONES.find((item) => item.value === zone);
  return `giờ Mỹ ${us ? us.label.split(" ")[0] : zone}`;
}

function parts(iso: string | Date, zone: string, options: Intl.DateTimeFormatOptions) {
  const formatter = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hourCycle: "h23", ...options });
  return Object.fromEntries(formatter.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
}

/** "20:00" in the zone. */
export function timeIn(iso: string | Date, zone: string): string {
  const p = parts(iso, zone, { hour: "2-digit", minute: "2-digit" });
  return `${p.hour}:${p.minute}`;
}

/** "20:00 EST": the time with the zone's own abbreviation, which shows daylight saving (EST / EDT). */
export function timeWithZone(iso: string | Date, zone: string): string {
  if (zone === VN_ZONE) return timeIn(iso, zone);
  const p = parts(iso, zone, { hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
  return `${p.hour}:${p.minute} ${p.timeZoneName}`;
}

/** "yyyy-mm-dd": the calendar day of the moment in the zone. */
export function dayKeyIn(iso: string | Date, zone: string): string {
  const p = parts(iso, zone, { year: "numeric", month: "2-digit", day: "2-digit" });
  return `${p.year}-${p.month}-${p.day}`;
}

/** "T4 25/11": the day heading, Vietnamese weekday and date. */
export function dayLabelIn(iso: string | Date, zone: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: zone,
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(iso));
}

/** The other zone's time beside the main one: "08:00 VN (+1 ngày)" when it falls on the next day there. */
export function secondaryTime(iso: string | Date, main: string, other: string): string {
  const base =
    dayKeyIn(iso, other) === dayKeyIn(iso, main)
      ? ""
      : dayKeyIn(iso, other) > dayKeyIn(iso, main)
        ? " (+1 ngày)"
        : " (−1 ngày)";
  return `${timeIn(iso, other)} ${other === VN_ZONE ? "VN" : "US"}${base}`;
}

/** The first day within `days` of `from` on which the zone's UTC offset changes (daylight saving), or null. */
export function nextClockChange(zone: string, from: Date = new Date(), days = 14): string | null {
  if (zone === VN_ZONE) return null;
  const offset = (at: Date) => {
    const p = parts(at, zone, { timeZoneName: "longOffset" });
    return p.timeZoneName;
  };
  let before = offset(from);
  for (let i = 1; i <= days; i++) {
    const at = new Date(from.getTime() + i * 86_400_000);
    const now = offset(at);
    if (now !== before) return dayKeyIn(at, zone);
    before = now;
  }
  return null;
}

/** The note shown beside a US zone in the fortnight before its clocks change; empty otherwise. */
export function clockChangeNote(zone: string, from: Date = new Date()): string {
  const day = nextClockChange(zone, from);
  if (!day) return "";
  const [, month, date] = day.split("-");
  return `Mỹ đổi giờ ngày ${date}/${month}: giờ đăng vẫn theo giờ Mỹ, nên giờ Việt Nam của bài sẽ lệch 1 tiếng từ hôm đó.`;
}
