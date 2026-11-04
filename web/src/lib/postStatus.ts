import type { StatusTone } from "@/components/StatusText";
import type { PostRow, PostStatus } from "./api";

/** Each status's label and the dot it is shown with (StatusText). */
export const POST_STATUS: Record<PostStatus, { label: string; tone: StatusTone }> = {
  pending: { label: "Đang chờ", tone: "idle" },
  scheduled: { label: "Đã hẹn lịch", tone: "waiting" },
  published: { label: "Đã đăng", tone: "success" },
  cancelled: { label: "Đã hủy", tone: "idle" },
  deleted: { label: "Đã xóa", tone: "danger" },
};

/** A post as "Bài đăng" shows it: one not on Facebook yet is on its way ("Đang đăng") or failed ("Thất bại"). */
export type ShownStatus = PostStatus | "failed";

export const SHOWN_STATUS: Record<ShownStatus, { label: string; tone: StatusTone }> = {
  ...POST_STATUS,
  pending: { label: "Đang đăng", tone: "active" },
  failed: { label: "Thất bại", tone: "danger" },
};

export function shownStatus(post: PostRow): ShownStatus {
  return post.attempt?.state === "failed" ? "failed" : post.status;
}
