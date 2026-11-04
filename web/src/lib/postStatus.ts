import type { PostRow, PostStatus } from "./api";

export const POST_STATUS: Record<PostStatus, { label: string; color: string }> = {
  pending: { label: "Đang chờ", color: "default" },
  scheduled: { label: "Đã hẹn lịch", color: "processing" },
  published: { label: "Đã đăng", color: "success" },
  cancelled: { label: "Đã hủy", color: "warning" },
  deleted: { label: "Đã xóa", color: "error" },
};

/** A post as "Bài đăng" shows it: one not on Facebook yet is on its way ("Đang đăng") or failed ("Thất bại"). */
export type ShownStatus = PostStatus | "failed";

export const SHOWN_STATUS: Record<ShownStatus, { label: string; color: string }> = {
  ...POST_STATUS,
  pending: { label: "Đang đăng", color: "processing" },
  failed: { label: "Thất bại", color: "red" },
};

export function shownStatus(post: PostRow): ShownStatus {
  return post.attempt?.state === "failed" ? "failed" : post.status;
}
