"use client";
import { canTakeDownPost } from "@/lib/permissions";

import { useMe } from "@/components/MeContext";
import { api, errorMessage, type Post, type VideoDetail } from "@/lib/api";
import { CloseCircleOutlined, DeleteOutlined, ExportOutlined, RedoOutlined, SyncOutlined } from "@ant-design/icons";
import { App, Button, Popconfirm, Space, Tooltip } from "antd";
import { useState } from "react";

type Action = "check" | "take-down" | "retry";

/** "Kiểm tra" re-reads a reel on Facebook, after a change made in Meta Business Suite, and for a post marked
 * deleted too. "Hủy đăng" for a post not public yet, "Xóa" for a public one; no take-down for one already closed.
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
  // Only whoever posted it cancels or deletes it (the api refuses anyone else).
  const { me } = useMe();
  const mine = canTakeDownPost(post, me.id);
  const [busy, setBusy] = useState<Action | null>(null);
  const closed = post.status === "cancelled" || post.status === "deleted";
  // A deleted post still gets "Kiểm tra": Facebook may have it after all (the app read it wrong, or a new token).
  const checkable = post.status !== "cancelled" && post.status !== "pending";
  if (post.status === "cancelled" && !compact) return null;
  const published = post.status === "published";

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

  // Why a button that applies is greyed out: one job at a time per video.
  const waiting = "Video đang chạy một việc khác (xem Nhật ký job), đợi xong rồi thao tác";
  const checkTip =
    "Đọc lại trạng thái bài trên Facebook — dùng khi bài đã lên nhưng tool ghi sai, hoặc sau khi dán token mới";
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
      disabled={disabled || closed || !mine}
    >
      {compact ? (
        <Tooltip
          title={
            closed
              ? "Bài đã hủy hoặc đã xóa"
              : !mine
                ? "Chỉ người đăng hoặc chủ Page mới hủy hoặc xóa được"
                : disabled
                  ? waiting
                  : published
                    ? "Xóa khỏi Facebook"
                    : "Hủy đăng"
          }
        >
          <Button
            size="small"
            type="text"
            danger={published}
            aria-label={published ? "Xóa" : "Hủy đăng"}
            icon={published ? <DeleteOutlined /> : <CloseCircleOutlined />}
            loading={busy === "take-down"}
            disabled={disabled || closed || !mine}
          />
        </Tooltip>
      ) : (
        <Button size="small" danger={published} loading={busy === "take-down"} disabled={disabled || !mine}>
          {published ? "Xóa" : "Hủy đăng"}
        </Button>
      )}
    </Popconfirm>
  );

  if (!compact) {
    return (
      <Space size={4}>
        {checkable && (
          <Tooltip title={checkTip}>
            <Button size="small" loading={busy === "check"} disabled={disabled} onClick={() => run("check")}>
              Kiểm tra
            </Button>
          </Tooltip>
        )}
        {!closed && takeDown}
      </Space>
    );
  }

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
      <Tooltip
        title={retryJobId === null ? "Chỉ thử lại được bài đăng thất bại" : disabled ? waiting : "Thử đăng lại bài này"}
      >
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
      <Tooltip
        title={
          !checkable ? "Chỉ kiểm tra được bài đã lên Facebook, đã hẹn giờ hoặc đã xóa" : disabled ? waiting : checkTip
        }
      >
        <Button
          size="small"
          type="text"
          aria-label="Kiểm tra"
          icon={<SyncOutlined />}
          loading={busy === "check"}
          disabled={disabled || !checkable}
          onClick={() => run("check")}
        />
      </Tooltip>
      {takeDown}
    </Space>
  );
}
