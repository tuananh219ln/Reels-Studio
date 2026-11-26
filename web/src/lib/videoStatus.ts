import type { StatusTone } from "@/components/StatusText";
import type { VideoRow } from "@/lib/api";

/** The review gate (api review.py): a rendered video that nobody has approved yet. */
export function needsReview(row: VideoRow): boolean {
  return row.review_status === "pending_review" && row.review_label !== "";
}

/** Why a video cannot be posted yet, or null: it waits for a member's approval (the api refuses it too). */
export const NEEDS_APPROVAL = "Cần duyệt video trước khi đăng";
export function postBlock(row: Pick<VideoRow, "review_status" | "review_label">): string | null {
  return row.review_label !== "" && row.review_status !== "approved" ? NEEDS_APPROVAL : null;
}

/** A video's status in words. A rendered video nobody approved reads "Chờ duyệt" (or "Đã bỏ") in place of "Chờ đăng". */
export function videoStatusLabel(row: VideoRow): string {
  return row.post_stage === "ready" && row.review_status !== "approved" && row.review_label
    ? row.review_label
    : row.status_label;
}

/** Where a video stands, as the status filters of the video list and of a group's "Video" tab offer it: the same
 * choices on both, every one listed even when no video is in it. A video with its MP4 is split by its posting
 * (api videos.post_stage): "Xong" said nothing about whether it was out (screen review 2026-11-12). */
export type VideoStatusFilter =
  "draft" | "working" | "review" | "ready" | "scheduled" | "posted" | "failed" | "outdated";

export const VIDEO_STATUS_FILTERS: { value: VideoStatusFilter; label: string; match: (row: VideoRow) => boolean }[] = [
  { value: "draft", label: "Nháp", match: (row) => row.status === "draft" },
  {
    value: "working",
    label: "Đang xử lý",
    match: (row) => !["draft", "done", "failed"].includes(row.status),
  },
  { value: "review", label: "Chờ duyệt", match: needsReview },
  { value: "ready", label: "Chờ đăng", match: (row) => row.post_stage === "ready" && row.review_status === "approved" },
  { value: "scheduled", label: "Đã hẹn giờ", match: (row) => row.post_stage === "scheduled" },
  { value: "posted", label: "Đã đăng", match: (row) => row.post_stage === "posted" },
  { value: "failed", label: "Lỗi", match: (row) => row.status === "failed" || row.rerender_failed },
  { value: "outdated", label: "MP4 cần render lại", match: (row) => row.mp4_outdated },
];

/** A group's "Video" tab has no room for one more status tab, so there "Chờ đăng" holds every rendered video not yet
 * posted, approved or not (each row still says "Chờ duyệt" when it is). */
export const TOPIC_STATUS_FILTERS = VIDEO_STATUS_FILTERS.filter((item) => item.value !== "review").map((item) =>
  item.value === "ready" ? { ...item, match: (row: VideoRow) => row.post_stage === "ready" } : item,
);

/** The dot of a video's status: grey a draft, blue a job, red an error, then by its posting. */
export function videoStatusTone(row: VideoRow): StatusTone {
  if (row.status === "draft") return "idle";
  if (row.status === "failed") return "danger";
  if (row.status !== "done") return row.status === "queued" ? "waiting" : "active";
  if (row.post_stage === "ready" && row.review_status !== "approved" && row.review_label) {
    return row.review_status === "rejected" ? "idle" : "warning";
  }
  if (row.post_stage === "posted") return "success";
  if (row.post_stage === "scheduled") return "waiting";
  return "done";
}
