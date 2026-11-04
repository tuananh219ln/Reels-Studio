"use client";

import { CommentOutlined } from "@ant-design/icons";
import { App, Button, Flex, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type Post } from "@/lib/api";
import StatusText, { type StatusTone } from "@/components/StatusText";

const STATE: Record<Post["comment"]["state"], { label: string; tone: StatusTone } | null> = {
  off: null,
  waiting: { label: "Sẽ tự bình luận khi bài lên", tone: "idle" },
  pending: { label: "Đang bình luận…", tone: "active" },
  done: { label: "Đã bình luận", tone: "success" },
  failed: { label: "Bình luận lỗi", tone: "danger" },
};

/** The affiliate comment the worker writes under the reel (api post_comments.py), and "Bình luận ngay" / "Cập nhật
 * bình luận" once the reel is live. The comment still has to be pinned on Facebook. `onChanged` reloads the post. */
export default function PostComment({ post, onChanged }: { post: Post; onChanged: () => void }) {
  const { message } = App.useApp();
  const [asking, setAsking] = useState(false);
  const { comment } = post;
  const live = post.status === "published" && post.url !== null;
  const shown = STATE[comment.state];

  // While the worker is about to write it, look again every few seconds.
  const waitingForWorker = comment.state === "pending";
  useEffect(() => {
    if (!waitingForWorker) return;
    const timer = setTimeout(onChanged, 4000);
    return () => clearTimeout(timer);
  }, [waitingForWorker, post, onChanged]);

  if (!shown && !live) return null;

  async function ask() {
    setAsking(true);
    try {
      await api(`/posts/${post.id}/comment`, "POST");
      onChanged();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAsking(false);
    }
  }

  return (
    <Flex vertical gap={2} data-testid="post-comment">
      <Flex gap={6} align="center" wrap>
        <CommentOutlined />
        {shown && <StatusText tone={shown.tone}>{shown.label}</StatusText>}
        {live && comment.state !== "pending" && (
          <Button size="small" type="link" loading={asking} onClick={ask} style={{ padding: 0 }}>
            {comment.state === "done" ? "Cập nhật bình luận" : "Bình luận ngay"}
          </Button>
        )}
      </Flex>
      {comment.error && (
        <Typography.Text type="danger" style={{ fontSize: 12 }}>
          {comment.error}
        </Typography.Text>
      )}
      {comment.state === "done" && comment.at && (
        <Tooltip title={comment.text}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Bình luận lúc {formatDateTime(comment.at)}, nhớ ghim trên Facebook
          </Typography.Text>
        </Tooltip>
      )}
    </Flex>
  );
}
