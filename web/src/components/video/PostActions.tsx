"use client";

import { CloseCircleOutlined, DeleteOutlined, ExportOutlined, RedoOutlined, SyncOutlined } from "@ant-design/icons";
import { App, Button, Popconfirm, Space, Tooltip } from "antd";
import { useState } from "react";
import { api, errorMessage, type Post, type VideoDetail } from "@/lib/api";

type Action = "check" | "take-down" | "retry";

/** "Kiểm tra" re-reads a reel on Facebook, after a change made in Meta Business Suite. "Hủy đăng" for a post not
 * public yet, "Xóa" for a public one; nothing for one already cancelled or deleted.
 *
 * `compact` ("Bài đăng") gives every post the same icon buttons in the same places, "Xem Reel" and "Thử lại" among
 * them, greyed out with the reason in their tooltip where they do not apply, so the rows line up. `retryJobId`: the
 * failed publish job "Thử lại" sends again. */
export default function PostActions({
  post,
  disabled,
  onDone,
  compact = false,
  retryJobId = null,
}: {
  post: Post;
  disabled: boolean;
  onDone: (video: VideoDetail) => void;
  compact?: boolean;
  retryJobId?: number | null;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState<Action | null>(null);
  const closed = post.status === "cancelled" || post.status === "deleted";
  if (closed && !compact) return null;
  const published = post.status === "published";
  const onFacebook = post.status !== "pending";

  async function run(action: Action) {
    setBusy(action);
    try {
      const path = action === "retry" ? `/jobs/${retryJobId}/retry` : `/posts/${post.id}/${action}`;
      onDone(await api<VideoDetail>(path, "POST"));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const checkTip = "Đọc lại trạng thái bài trên Facebook, khi đã hủy, đổi giờ hoặc xóa trong Meta Business Suite";
  const takeDown = (
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
      disabled={disabled || closed}
    >
      {compact ? (
        <Tooltip title={closed ? "Bài đã hủy hoặc đã xóa" : published ? "Xóa khỏi Facebook" : "Hủy đăng"}>
          <Button
            size="small"
            type="text"
            danger={published}
            aria-label={published ? "Xóa" : "Hủy đăng"}
            icon={published ? <DeleteOutlined /> : <CloseCircleOutlined />}
            loading={busy === "take-down"}
            disabled={disabled || closed}
          />
        </Tooltip>
      ) : (
        <Button size="small" danger={published} loading={busy === "take-down"} disabled={disabled}>
          {published ? "Xóa" : "Hủy đăng"}
        </Button>
      )}
    </Popconfirm>
  );

  if (!compact) {
    return (
      <Space size={4}>
        {onFacebook && (
          <Tooltip title={checkTip}>
            <Button size="small" loading={busy === "check"} disabled={disabled} onClick={() => run("check")}>
              Kiểm tra
            </Button>
          </Tooltip>
        )}
        {takeDown}
      </Space>
    );
  }

  const live = onFacebook && !closed;
  return (
    <Space size={2}>
      <Tooltip title={post.url ? "Xem Reel trên Facebook" : "Bài chưa công khai trên Facebook"}>
        {post.url ? (
          <Button
            size="small"
            type="text"
            aria-label="Xem Reel"
            icon={<ExportOutlined />}
            href={post.url}
            target="_blank"
            rel="noreferrer"
          />
        ) : (
          <Button size="small" type="text" aria-label="Xem Reel" icon={<ExportOutlined />} disabled />
        )}
      </Tooltip>
      <Tooltip title={retryJobId !== null ? "Thử đăng lại bài này" : "Chỉ thử lại được bài đăng thất bại"}>
        <Button
          size="small"
          type="text"
          aria-label="Thử lại"
          icon={<RedoOutlined />}
          loading={busy === "retry"}
          disabled={disabled || retryJobId === null}
          onClick={() => run("retry")}
        />
      </Tooltip>
      <Tooltip title={live ? checkTip : "Chỉ kiểm tra được bài đã lên Facebook hoặc đã hẹn giờ"}>
        <Button
          size="small"
          type="text"
          aria-label="Kiểm tra"
          icon={<SyncOutlined />}
          loading={busy === "check"}
          disabled={disabled || !live}
          onClick={() => run("check")}
        />
      </Tooltip>
      {takeDown}
    </Space>
  );
}
