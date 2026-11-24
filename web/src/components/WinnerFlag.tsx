"use client";

import { api, errorMessage, type VideoRow } from "@/lib/api";
import { CopyOutlined, TrophyOutlined } from "@ant-design/icons";
import { App, Button, Flex, Popconfirm, Tag, Tooltip } from "antd";
import { useState } from "react";

/** The "winner" flag of a video: its 48-hour views are 10× its Page's median or more (worked out by the api when the
 * list is read, never stored), and "Tạo 3 biến thể" beside it: three draft copies named for what to change. */
export default function WinnerFlag({ video, onChanged }: { video: VideoRow; onChanged?: () => void }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const post = video.post;
  if (!post?.is_winner) return null;

  async function makeVariants() {
    setBusy(true);
    try {
      await api(`/videos/${video.id}/variants`, "POST");
      message.success("Đã tạo 3 video nháp: đổi hook, đổi 1–2 món, đổi dạng");
      onChanged?.();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex gap={6} align="center" wrap data-testid="winner-flag">
      <Tooltip title={`View 48h của video gấp ${post.times_median ?? "10"}× trung vị Page (60 ngày)`}>
        <Tag color="gold" icon={<TrophyOutlined />} style={{ marginInlineEnd: 0 }}>
          Winner{post.times_median ? ` ${post.times_median}×` : ""}
        </Tag>
      </Tooltip>
      <Popconfirm
        title="Tạo 3 video nháp từ video này?"
        description="Bản 1 đổi hook, bản 2 đổi 1–2 món, bản 3 đổi dạng. Chỉ sao chép, không gọi AI; bạn (hoặc trợ lý qua MCP) sửa từng bản rồi render."
        okText="Tạo 3 bản"
        cancelText="Không"
        onConfirm={makeVariants}
      >
        <Button size="small" icon={<CopyOutlined />} loading={busy}>
          Tạo 3 biến thể
        </Button>
      </Popconfirm>
    </Flex>
  );
}
