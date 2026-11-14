import type { Post, VideoDetail } from "./api";

export type PlatformKey = "facebook" | "tiktok" | "youtube" | "instagram";

export const PLATFORM_LABELS: Record<PlatformKey, string> = {
  facebook: "Facebook",
  tiktok: "TikTok",
  youtube: "YouTube Shorts",
  instagram: "Instagram",
};

/** The platforms the app posts to by itself; YouTube Shorts and Instagram are posted by hand and recorded. */
export const AUTO_PLATFORMS: PlatformKey[] = ["facebook", "tiktok"];

/**
 * Where a video stands on one platform, as the "Đăng bài" tab's rows, the progress line and the toast read it:
 * `ok` out (when, and its link), `err` the last try failed (why, and the job "Thử lại" sends again), `wait` on its way
 * or scheduled.
 */
export type PlatformResult = {
  platform: PlatformKey;
  state: "ok" | "err" | "wait";
  /** When it went out, or is due. */
  at: string | null;
  url: string | null;
  error: string | null;
  /** The failed job "Thử lại" retries; null when there is none to retry. */
  retryJobId: number | null;
  /** The Facebook post the row is about, for its actions. */
  post: Post | null;
};

/** Every platform the video has been tried on, in the grid's order; a platform never tried is left out. */
export function platformResults(video: VideoDetail): PlatformResult[] {
  const results: PlatformResult[] = [];
  const failed = video.failed_job;

  // Facebook: the newest post that is out, else one due, else the one being sent (or whose sending failed).
  const facebook = video.publications;
  const live = facebook.find((post) => post.status === "published");
  const scheduled = facebook.find((post) => post.status === "scheduled");
  const pending = facebook.find((post) => post.status === "pending");
  if (live) {
    results.push(row("facebook", "ok", live.at, live.url, live));
  } else if (scheduled) {
    results.push(row("facebook", "wait", scheduled.scheduled_at ?? scheduled.at, scheduled.url, scheduled));
  } else if (pending && failed?.kind === "publish") {
    results.push({ ...row("facebook", "err", null, null, pending), error: failed.error, retryJobId: failed.id });
  } else if (pending) {
    results.push(row("facebook", "wait", null, null, pending));
  }

  // TikTok: a post sent through the API ends "published" or, when TikTok refused it, "cancelled".
  const tiktok = video.tiktok_posts;
  const tiktokLive = tiktok.find((post) => post.status === "published");
  const tiktokPending = tiktok.find((post) => post.status === "pending");
  if (tiktokLive) {
    results.push(row("tiktok", "ok", tiktokLive.at, tiktokLive.url, null));
  } else if (tiktokPending) {
    results.push(row("tiktok", "wait", null, null, null));
  } else if (tiktok.length > 0) {
    const retry = failed?.kind === "tiktok_publish" ? failed : null;
    results.push({
      ...row("tiktok", "err", null, null, null),
      error: retry?.error ?? "TikTok không nhận video",
      retryJobId: retry?.id ?? null,
    });
  }

  for (const platform of ["youtube", "instagram"] as const) {
    const manual = video.manual_posts.find((post) => post.platform === platform);
    if (manual) results.push(row(platform, "ok", manual.at, manual.url, null));
  }
  return results;
}

function row(
  platform: PlatformKey,
  state: PlatformResult["state"],
  at: string | null,
  url: string | null,
  post: Post | null,
): PlatformResult {
  return { platform, state, at, url, error: null, retryJobId: null, post };
}

/** "Đã đăng lên X/Y nền tảng": X out, of the Y tried, and when the newest went out. */
export function postCount(results: PlatformResult[]): { out: number; tried: number; last: string | null } {
  const out = results.filter((result) => result.state === "ok");
  const last = out
    .map((result) => result.at)
    .filter((at): at is string => at !== null)
    .sort()
    .at(-1);
  return { out: out.length, tried: results.length, last: last ?? null };
}
