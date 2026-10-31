"use client";

import { Space, Tag } from "antd";
import type { VideoRow } from "@/lib/api";

const COLORS: Record<VideoRow["status"], string> = {
  draft: "default",
  queued: "blue",
  writing: "processing",
  rendering: "processing",
  publishing: "processing",
  done: "success",
  failed: "error",
};

export default function VideoStatusTags({ video }: { video: VideoRow }) {
  return (
    <Space size={4} wrap>
      <Tag color={COLORS[video.status]} data-testid="video-status">
        {video.status_label}
      </Tag>
      {video.rerender_failed && <Tag color="error">Render lại lỗi</Tag>}
      {video.mp4_outdated && <Tag color="warning">MP4 chưa cập nhật theo bản sửa</Tag>}
    </Space>
  );
}
