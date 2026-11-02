import type { PostStatus } from "./api";

export const POST_STATUS: Record<PostStatus, { label: string; color: string }> = {
  pending: { label: "Đang chờ", color: "default" },
  scheduled: { label: "Đã hẹn lịch", color: "processing" },
  published: { label: "Đã đăng", color: "success" },
  cancelled: { label: "Đã hủy", color: "warning" },
  deleted: { label: "Đã xóa", color: "error" },
};
