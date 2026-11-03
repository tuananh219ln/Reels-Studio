"use client";

import { EyeOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Flex, Tooltip, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, formatDateTime, type Post, type PostNumbers } from "@/lib/api";

const count = new Intl.NumberFormat("vi-VN");

/** "12.345", or "—" when Facebook did not give the number. */
export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : count.format(value);
}

/** Views of a post for sorting: a post not read yet sorts after every read one. */
export function viewsOf(post: Post): number {
  return post.metrics.latest?.views ?? -1;
}

function details(numbers: PostNumbers): string {
  return [
    `${formatCount(numbers.shares)} share`,
    `${formatCount(numbers.comments)} bình luận`,
    `${formatCount(numbers.reactions)} cảm xúc`,
  ].join(" · ");
}

/** A post's numbers on Facebook and when they were read; nothing for a post never public. With `onAsked`, a
 * "Cập nhật view" button asks the worker to read them again. */
export default function PostMetrics({ post, onAsked }: { post: Post; onAsked?: () => void }) {
  const { message } = App.useApp();
  const [asking, setAsking] = useState(false);
  const { latest, at_48h: mark, error, pending } = post.metrics;
  const isPublic = post.status === "published" && post.url !== null;
  if (!latest && !error && !isPublic) return null;

  async function ask() {
    setAsking(true);
    try {
      await api(`/posts/${post.id}/metrics`, "POST");
      onAsked?.();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAsking(false);
    }
  }

  return (
    <Flex vertical gap={2} data-testid="post-metrics">
      {latest ? (
        <>
          <Typography.Text strong>
            <EyeOutlined /> <span data-testid="post-views">{formatCount(latest.views)}</span> view
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {details(latest)}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Đo lúc {formatDateTime(latest.measured_at)}
            {mark && ` · mốc 48 giờ: ${formatCount(mark.views)} view`}
          </Typography.Text>
        </>
      ) : (
        isPublic && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Chưa có số view, app tự đo sau khi đăng 1 giờ
          </Typography.Text>
        )
      )}
      {error && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          Lần đo gần nhất lỗi: {error}
        </Typography.Text>
      )}
      {onAsked && isPublic && (
        <div>
          <Tooltip title="App tự đo mỗi ngày trong 14 ngày đầu; bấm để đo lại ngay">
            <Button size="small" icon={<ReloadOutlined />} loading={asking || pending} disabled={pending} onClick={ask}>
              {pending ? "Đang đo view" : "Cập nhật view"}
            </Button>
          </Tooltip>
        </div>
      )}
    </Flex>
  );
}
