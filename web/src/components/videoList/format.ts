import { formatDateTime, type VideoRow, type VideoRowPost } from "@/lib/api";

/** From this many times its Page's median at 48 hours a post is drawn as a standout (docs/content.md). */
export const STANDOUT_TIMES = 10;
/** From this many times its Page's median at 48 hours a Facebook video without a TikTok version suggests making one. */
export const TIKTOK_NUDGE_TIMES = 3;

/** Accents and case ignored, so "rau mam" finds "Rau mầm". */
export function plain(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
}

/** "1.234": a count as the team writes it. */
export function count(value: number): string {
  return value.toLocaleString("vi-VN");
}

/** "800", "12,4K", "1,2M": how the team says view counts. */
export function compactViews(views: number): string {
  const short = (value: number, unit: string) =>
    `${value.toLocaleString("vi-VN", { maximumFractionDigits: value < 100 ? 1 : 0 })}${unit}`;
  if (views >= 1_000_000) return short(views / 1_000_000, "M");
  if (views >= 1_000) return short(views / 1_000, "K");
  return views.toLocaleString("vi-VN");
}

export function percent(rate: number): string {
  return `${(rate * 100).toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

/** "03/11 07:00" (or "03/11" without `time`), in Vietnam time; the year only when it is not this one. */
export function shortDate(iso: string, time = true): string {
  const full = formatDateTime(iso); // "03/11/2026 07:00"
  const thisYear = formatDateTime(new Date().toISOString()).slice(6, 10);
  const day = full.slice(6, 10) === thisYear ? full.slice(0, 5) : full.slice(0, 10);
  return time ? `${day} ${full.slice(11, 16)}` : day;
}

/** The topic a video was made from, only when its title does not already say it: a title that repeats the topic gave
 * the list two near-identical lines. */
function otherTopic(row: VideoRow): string {
  const title = plain(row.title || "");
  const topic = plain(row.topic);
  return !topic || title.includes(topic) || topic.includes(title) ? "" : row.topic;
}

/** "Vườn nhà, 03/11/2026 07:00 (+1 trang)": the post a row counts, and how many Pages more. */
export function postLine(post: VideoRowPost): string {
  const pages = post.pages > 1 ? `${post.fanpage} +${post.pages - 1}` : post.fanpage;
  return `${pages}, ${post.state === "scheduled" ? "hẹn" : "đăng"} ${formatDateTime(post.at)}`;
}

/** The grey line under a video's title, the same on every list: its plan day, the topic when the title does not say
 * it, where and when it is out or set to go (else the Page queue it waits in, or the time suggested), its content
 * type and products. "Chưa đăng" when there is nothing to say. */
export function videoDetails(row: VideoRow): string {
  const parts: string[] = [];
  if (row.plan_day) parts.push(`Ngày ${row.plan_day}`);
  if (otherTopic(row)) parts.push(otherTopic(row));
  if (row.post) {
    parts.push(postLine(row.post));
  } else if (row.queue) {
    parts.push(
      row.queue.error ? `Hàng chờ ${row.queue.fanpage}: ${row.queue.error}` : `Trong hàng chờ ${row.queue.fanpage}`,
    );
  } else if (row.suggested_post_at) {
    parts.push(`Gợi ý đăng ${formatDateTime(row.suggested_post_at)}`);
  }
  if (row.content_type) parts.push(row.content_type);
  if (row.product_count) parts.push(`${row.product_count} sản phẩm`);
  return parts.length ? parts.join(", ") : "Chưa đăng";
}

/** A Facebook video doing well at 48 hours, neither on TikTok itself nor with a TikTok version yet: the list offers
 * to make one. */
export function wantsTikTok(row: VideoRow): boolean {
  return (
    row.platform === "facebook" &&
    !row.has_tiktok_version &&
    !row.posted_on.includes("tiktok") &&
    row.post?.state === "posted" &&
    row.post.times_median !== null &&
    row.post.times_median >= TIKTOK_NUDGE_TIMES
  );
}
