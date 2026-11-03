"use client";

import { EyeOutlined, ReloadOutlined, TrophyOutlined } from "@ant-design/icons";
import { App, Button, Flex, Tag, Tooltip, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, formatDateTime, type Post, type PostNumbers } from "@/lib/api";

const count = new Intl.NumberFormat("vi-VN");

/** "12.345", or "—" when Facebook did not give the number. */
export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : count.format(value);
}

const percent = new Intl.NumberFormat("vi-VN", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
});

/** "0,25%", or "—". */
export function formatRate(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : percent.format(value);
}

/** The team's share/view goal (docs/content.md); the api's KPIs use the same. */
export const SHARE_GOAL = 0.002;

/** "Video thắng": 10× its Page's median views at 48 hours. */
export function WinnerTag({ post }: { post: Post }) {
  const { is_winner, times_median } = post.metrics.analysis;
  if (!is_winner) return null;
  return (
    <Tooltip title={`View ở mốc 48 giờ gấp ${times_median}× trung vị của Page: nên làm 3 biến thể bằng "Nhân bản"`}>
      <Tag color="gold" icon={<TrophyOutlined />} style={{ marginInlineEnd: 0 }} data-testid="winner-tag">
        Video thắng
      </Tag>
    </Tooltip>
  );
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
  const { latest, at_48h: mark, error, pending, analysis } = post.metrics;
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
          {mark && <Analysis analysis={analysis} />}
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

/** What the 48-hour numbers mean: against the Page's median, and the share/view goal. */
function Analysis({ analysis }: { analysis: Post["metrics"]["analysis"] }) {
  const rate = analysis.share_rate;
  return (
    <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="post-analysis">
      {analysis.times_median !== null
        ? `Gấp ${String(analysis.times_median).replace(".", ",")}× trung vị Page (${formatCount(analysis.median_views)})`
        : "Chưa đủ dữ liệu để so trung vị"}
      {" · share/view "}
      <Typography.Text
        type={rate === null ? "secondary" : rate >= SHARE_GOAL ? "success" : "warning"}
        style={{ fontSize: 12 }}
      >
        {formatRate(rate)}
      </Typography.Text>
    </Typography.Text>
  );
}
