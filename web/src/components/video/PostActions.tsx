"use client";

import { App, Button, Popconfirm, Space, Tooltip } from "antd";
import { useState } from "react";
import { api, errorMessage, type Post, type VideoDetail } from "@/lib/api";

/** "Kiểm tra" re-reads a reel on Facebook, after a change made in Meta Business Suite. "Hủy đăng" for a post not
 * public yet, "Xóa" for a public one; nothing for one already cancelled or deleted. */
export default function PostActions({
  post,
  disabled,
  onDone,
}: {
  post: Post;
  disabled: boolean;
  onDone: (video: VideoDetail) => void;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState<"check" | "take-down" | null>(null);
  if (post.status === "cancelled" || post.status === "deleted") return null;
  const published = post.status === "published";
  const onFacebook = post.status !== "pending";

  async function run(action: "check" | "take-down") {
    setBusy(action);
    try {
      onDone(await api<VideoDetail>(`/posts/${post.id}/${action}`, "POST"));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Space size={4}>
      {onFacebook && (
        <Tooltip title="Đọc lại trạng thái bài trên Facebook, khi đã hủy, đổi giờ hoặc xóa trong Meta Business Suite">
          <Button size="small" loading={busy === "check"} disabled={disabled} onClick={() => run("check")}>
            Kiểm tra
          </Button>
        </Tooltip>
      )}
      <Popconfirm
        title={published ? "Xóa bài này khỏi Facebook?" : "Hủy đăng bài này?"}
        description={
          published
            ? "Không khôi phục được trên Facebook. Lịch sử vẫn giữ trong tool."
            : "Facebook sẽ không đăng bài này."
        }
        okText={published ? "Xóa" : "Hủy đăng"}
        okButtonProps={{ danger: true }}
        cancelText="Không"
        onConfirm={() => run("take-down")}
        disabled={disabled}
      >
        <Button size="small" danger={published} loading={busy === "take-down"} disabled={disabled}>
          {published ? "Xóa" : "Hủy đăng"}
        </Button>
      </Popconfirm>
    </Space>
  );
}
