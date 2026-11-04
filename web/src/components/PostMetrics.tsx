"use client";

import { EyeOutlined, ReloadOutlined, WarningOutlined } from "@ant-design/icons";
import { App, Button, Flex, Tooltip, Typography } from "antd";
import { useState } from "react";
import PostInsights from "@/components/PostInsights";
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

/** Views of a post for sorting: a post not read yet sorts after every read one. */
export function viewsOf(post: Post): number {
  return post.metrics.latest?.views ?? -1;
}

function details(numbers: PostNumbers): string {
  return [
    `${formatCount(numbers.shares)} share`,
    `${formatCount(numbers.comments)} bình luận`,
    `${formatCount(numbers.reactions)} cảm xúc`,
  ].join(", ");
}

const seconds = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });

/** "Xem TB 8,4 giây (42%), tiếp cận 900", or "" when Facebook gave neither. */
function watching(numbers: PostNumbers): string {
  const parts = [];
  if (numbers.avg_watch_seconds !== null) {
    const ratio = numbers.watch_ratio !== null ? ` (${formatRate(numbers.watch_ratio)})` : "";
    parts.push(`Xem TB ${seconds.format(numbers.avg_watch_seconds)} giây${ratio}`);
  }
  if (numbers.reach !== null) parts.push(`tiếp cận ${formatCount(numbers.reach)}`);
  return parts.join(", ");
}

/** A post's numbers on Facebook and when they were read; nothing for a post never public. With `onAsked`, a
 * "Cập nhật view" button asks the worker to read them again. `compact` (the list) keeps it to one line: the
 * views and an icon button, the rest in a tooltip. */
export default function PostMetrics({
  post,
  onAsked,
  compact = false,
}: {
  post: Post;
  onAsked?: () => void;
  compact?: boolean;
}) {
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

  const askTip = "App tự đo mỗi ngày trong 14 ngày đầu; bấm để đo lại ngay";

  if (compact) {
    const tip = (
      <Flex vertical gap={2}>
        {latest ? (
          <>
            <span>{details(latest)}</span>
            {watching(latest) && <span>{watching(latest)}</span>}
            <span>
              Đo lúc {formatDateTime(latest.measured_at)}
              {mark && `, mốc 48 giờ: ${formatCount(mark.views)} view`}
            </span>
            {mark && <AnalysisText analysis={analysis} />}
          </>
        ) : (
          <span>Chưa có số view, app tự đo sau khi đăng 1 giờ</span>
        )}
        {error && <span>Lần đo gần nhất lỗi: {error}</span>}
      </Flex>
    );
    return (
      <Flex align="center" gap={6} wrap={false} data-testid="post-metrics">
        <Tooltip title={tip}>
          {latest ? (
            <Typography.Text strong style={{ whiteSpace: "nowrap" }}>
              <EyeOutlined /> <span data-testid="post-views">{formatCount(latest.views)}</span> view
            </Typography.Text>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
              Chưa có view
            </Typography.Text>
          )}
        </Tooltip>
        {error && (
          <Tooltip title={`Lần đo gần nhất lỗi: ${error}`}>
            <Typography.Text type="warning" data-testid="post-metrics-error">
              <WarningOutlined aria-label="Lần đo gần nhất lỗi" />
            </Typography.Text>
          </Tooltip>
        )}
        <PostInsights post={post} compact />
        {onAsked && isPublic && (
          <Tooltip title={pending ? "Đang đo view" : `Cập nhật view: ${askTip.toLowerCase()}`}>
            <Button
              size="small"
              type="text"
              aria-label={pending ? "Đang đo view" : "Cập nhật view"}
              icon={<ReloadOutlined />}
              loading={asking || pending}
              disabled={pending}
              onClick={ask}
            />
          </Tooltip>
        )}
      </Flex>
    );
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
          {watching(latest) && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="post-watching">
              {watching(latest)}
            </Typography.Text>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Đo lúc {formatDateTime(latest.measured_at)}
            {mark && `, mốc 48 giờ: ${formatCount(mark.views)} view`}
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
      {(latest || (onAsked && isPublic)) && (
        <Flex gap={8} wrap>
          <PostInsights post={post} />
          {onAsked && isPublic && (
            <Tooltip title={askTip}>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={asking || pending}
                disabled={pending}
                onClick={ask}
              >
                {pending ? "Đang đo view" : "Cập nhật view"}
              </Button>
            </Tooltip>
          )}
        </Flex>
      )}
    </Flex>
  );
}

/** The 48-hour reading as plain text, for the list's tooltip. */
function AnalysisText({ analysis }: { analysis: Post["metrics"]["analysis"] }) {
  return (
    <span>
      {analysis.times_median !== null
        ? `Gấp ${String(analysis.times_median).replace(".", ",")}× trung vị Page (${formatCount(analysis.median_views)})`
        : "Chưa đủ dữ liệu để so trung vị"}
      {`, share/view ${formatRate(analysis.share_rate)}`}
    </span>
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
      {", share/view "}
      <Typography.Text
        type={rate === null ? "secondary" : rate >= SHARE_GOAL ? "success" : "warning"}
        style={{ fontSize: 12 }}
      >
        {formatRate(rate)}
      </Typography.Text>
    </Typography.Text>
  );
}
