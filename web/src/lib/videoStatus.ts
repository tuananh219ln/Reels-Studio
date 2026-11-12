import type { StatusTone } from "@/components/StatusText";
import type { VideoRow } from "@/lib/api";

/** Where a video stands, as the status filters of the video list and of a group's "Video" tab offer it: the same
 * choices on both, every one listed even when no video is in it. A video with its MP4 is split by its posting
 * (api videos.post_stage): "Xong" said nothing about whether it was out (screen review 2026-11-12). */
export type VideoStatusFilter = "draft" | "working" | "ready" | "scheduled" | "posted" | "failed" | "outdated";

export const VIDEO_STATUS_FILTERS: { value: VideoStatusFilter; label: string; match: (row: VideoRow) => boolean }[] = [
  { value: "draft", label: "Nháp", match: (row) => row.status === "draft" },
  {
    value: "working",
    label: "Đang xử lý",
    match: (row) => !["draft", "done", "failed"].includes(row.status),
  },
  { value: "ready", label: "Chờ đăng", match: (row) => row.post_stage === "ready" },
  { value: "scheduled", label: "Đã lên lịch", match: (row) => row.post_stage === "scheduled" },
  { value: "posted", label: "Đã đăng", match: (row) => row.post_stage === "posted" },
  { value: "failed", label: "Lỗi", match: (row) => row.status === "failed" || row.rerender_failed },
  { value: "outdated", label: "MP4 cần render lại", match: (row) => row.mp4_outdated },
];

/** The dot of a video's status: grey a draft, blue a job, red an error, then by its posting. */
export function videoStatusTone(row: VideoRow): StatusTone {
  if (row.status === "draft") return "idle";
  if (row.status === "failed") return "danger";
  if (row.status !== "done") return row.status === "queued" ? "waiting" : "active";
  if (row.post_stage === "posted") return "success";
  if (row.post_stage === "scheduled") return "waiting";
  return "done";
}
