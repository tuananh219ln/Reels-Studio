"use client";

import { formatCount } from "@/components/PostMetrics";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatDayTime, type BoardCell, type BoardItem, type BoardPlatform } from "@/lib/api";
import { DownloadOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Flex, Spin, Tooltip, Typography, theme } from "antd";
import { useState } from "react";
import { formatDayMonth, hoursAgo, SourceChip, STATE_LABEL, STATE_TONE } from "./boardText";

const SMALL = { fontSize: 12 } as const;

/** One platform's cell of a video's row on "Bài đăng": where the video stands there, and what to do next. */
export default function PlatformCell({
  platform,
  cell,
  video,
  onPaste,
  onDownload,
  onChanged,
}: {
  platform: BoardPlatform;
  cell: BoardCell | null;
  video: BoardItem["video"];
  onPaste: (videoId: number, platform: BoardPlatform) => void;
  onDownload: (videoId: number, platform: BoardPlatform) => void;
  onChanged: () => void;
}) {
  const { token } = theme.useToken();
  const { message } = App.useApp();
  const [retrying, setRetrying] = useState(false);

  const videoId = video.id;
  if (cell === null) {
    if (videoId === null) return <Typography.Text type="secondary">—</Typography.Text>;
    if (!video.has_mp4) {
      return (
        <Typography.Text type="secondary" style={SMALL}>
          Chưa có MP4
        </Typography.Text>
      );
    }
    if (platform === "facebook") {
      return (
        <Button type="primary" size="small" href={`/videos/${videoId}?publish=`}>
          Đăng / Hẹn giờ
        </Button>
      );
    }
    return (
      <Flex gap={4} wrap>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => onDownload(videoId, platform)}>
          Tải MP4
        </Button>
        <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={() => onPaste(videoId, platform)}>
          Dán link
        </Button>
      </Flex>
    );
  }

  const label = <StatusText tone={STATE_TONE[cell.state]}>{STATE_LABEL[cell.state]}</StatusText>;
  switch (cell.state) {
    case "pending_link":
      return (
        <button
          type="button"
          onClick={() => videoId !== null && onPaste(videoId, platform)}
          aria-label={`Dán link ${platform === "tiktok" ? "TikTok" : "YouTube"} cho video ${video.name}`}
          style={{
            all: "unset",
            cursor: "pointer",
            display: "flex",
            flexDirection: "column",
            gap: 2,
            padding: "4px 8px",
            borderRadius: 6,
            background: token.colorWarningBg,
            border: `1px solid ${token.colorWarningBorder}`,
          }}
        >
          {label}
          <span style={{ ...SMALL, color: cell.pending_stale ? token.colorErrorText : token.colorTextSecondary }}>
            Tải MP4 {cell.pending_since ? formatDayMonth(cell.pending_since) : ""} ·{" "}
            {cell.pending_since ? hoursAgo(cell.pending_since) : ""}
          </span>
        </button>
      );
    case "scheduled":
      return (
        <Flex vertical gap={2}>
          {label}
          <Typography.Text type="secondary" style={SMALL}>
            {cell.scheduled_at ? formatDayTime(cell.scheduled_at) : ""}
            {cell.channel_label ? ` · ${cell.channel_label}` : ""}
          </Typography.Text>
        </Flex>
      );
    case "publishing":
      return label;
    case "failed":
      return (
        <Flex vertical gap={2} align="flex-start">
          <Tooltip title={cell.error ?? undefined}>{label}</Tooltip>
          {cell.retry_job_id !== null && (
            <Button
              size="small"
              loading={retrying}
              onClick={async () => {
                setRetrying(true);
                try {
                  await api(`/jobs/${cell.retry_job_id}/retry`, "POST");
                  message.success("Đã gửi thử lại");
                  onChanged();
                } catch (err) {
                  message.error(errorMessage(err));
                } finally {
                  setRetrying(false);
                }
              }}
            >
              Thử lại
            </Button>
          )}
        </Flex>
      );
    case "removed":
      return (
        <Flex vertical gap={2}>
          {label}
          <Typography.Text type="secondary" style={SMALL}>
            Link không còn truy cập{cell.closed_at ? ` · ${formatDayMonth(cell.closed_at)}` : ""}
          </Typography.Text>
        </Flex>
      );
  }

  // Published: the views of every post out there, with what they add up to and where they come from; a spinner
  // while "Cập nhật view" waits for the worker.
  const updated = cell.metrics_updated_at ? `Cập nhật lần cuối ${formatDayTime(cell.metrics_updated_at)}` : undefined;
  return (
    <Flex vertical gap={2}>
      <Tooltip title={cell.views === null && cell.hint ? cell.hint : updated}>
        <span>
          <StatusText tone="success">{cell.views === null ? "— view" : `${formatCount(cell.views)} view`}</StatusText>
          {cell.refreshing && <Spin size="small" style={{ marginLeft: 6 }} aria-label="Đang cập nhật view" />}
        </span>
      </Tooltip>
      <Flex gap={6} align="center" wrap>
        <Typography.Text type="secondary" style={SMALL}>
          {cell.views === null
            ? `Đăng ${cell.published_at ? formatDayTime(cell.published_at) : ""} · chờ số liệu`
            : `${cell.channel_label ?? ""}${cell.views_48h !== null ? ` · 48h: ${formatCount(cell.views_48h)}` : ""}`}
        </Typography.Text>
        <SourceChip source={cell.source} />
      </Flex>
    </Flex>
  );
}
