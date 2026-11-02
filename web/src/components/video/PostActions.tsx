"use client";

import { App, Button, Popconfirm } from "antd";
import { useState } from "react";
import { api, errorMessage, type Post, type VideoDetail } from "@/lib/api";

/** "Hủy đăng" for a post not public yet, "Xóa" for a public one; nothing for one already cancelled or deleted. */
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
  const [busy, setBusy] = useState(false);
  if (post.status === "cancelled" || post.status === "deleted") return null;
  const published = post.status === "published";

  async function takeDown() {
    setBusy(true);
    try {
      onDone(await api<VideoDetail>(`/posts/${post.id}/take-down`, "POST"));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
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
      onConfirm={takeDown}
      disabled={disabled}
    >
      <Button size="small" danger={published} loading={busy} disabled={disabled}>
        {published ? "Xóa" : "Hủy đăng"}
      </Button>
    </Popconfirm>
  );
}
