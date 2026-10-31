import type { PostRow } from "./api";

export const POST_STATUS: Record<PostRow["status"], { label: string; color: string }> = {
  scheduled: { label: "Đã hẹn lịch", color: "processing" },
  published: { label: "Đã đăng", color: "success" },
};
