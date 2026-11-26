"use client";

import { SwapOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Flex, Typography } from "antd";
import { useState } from "react";
import { formatDateTime, formatDecimal, type VideoDetail } from "@/lib/api";
import ImportMp4Modal from "./ImportMp4Modal";

/** The page of a finished MP4 ("MP4 tải lên") in place of the scene list: the player, what ffprobe read, who sent the
 * file and the sender's note, and "Thay MP4" until it is posted. */
export default function UploadedMp4({
  video,
  onReplaced,
}: {
  video: VideoDetail;
  onReplaced: (video: VideoDetail) => void;
}) {
  const [replacing, setReplacing] = useState(false);
  const info = video.media_info;
  const upload = video.upload;
  const posted = video.publications.some((post) => post.status === "published");
  const facts = info
    ? [
        `${info.width}×${info.height}`,
        `${formatDecimal(info.duration_s)}s`,
        info.has_audio ? "có tiếng" : "không có tiếng",
      ].join(" · ")
    : null;
  const sender = upload
    ? `Tải lên bởi ${upload.via === "assistant" ? `${video.assistant_app || "Trợ lý AI"} (MCP)` : (upload.uploaded_by ?? "thành viên")} · ${formatDateTime(upload.uploaded_at)}`
    : null;
  return (
    <Flex vertical gap={16} data-testid="uploaded-mp4">
      {video.warnings?.map((warning) => (
        <Alert key={warning} type="warning" showIcon title={warning} />
      ))}
      <Card>
        <Flex vertical gap={12} align="flex-start">
          {video.mp4 && (
            <video
              key={video.mp4.url}
              src={video.mp4.url}
              poster={video.thumbnail_url ?? undefined}
              controls
              preload="metadata"
              style={{ width: "100%", maxWidth: 360, maxHeight: 640, borderRadius: 8, background: "#000" }}
              data-testid="uploaded-player"
            />
          )}
          {facts && (
            <Typography.Text data-testid="uploaded-facts" type="secondary">
              {facts}
            </Typography.Text>
          )}
          {sender && <Typography.Text type="secondary">{sender}</Typography.Text>}
          {upload?.note && (
            <Typography.Paragraph type="secondary" style={{ margin: 0 }} data-testid="uploaded-note">
              Ghi chú: {upload.note}
            </Typography.Paragraph>
          )}
          {!posted && (
            <Button icon={<SwapOutlined />} disabled={video.locked} onClick={() => setReplacing(true)}>
              Thay MP4
            </Button>
          )}
        </Flex>
      </Card>
      <ImportMp4Modal
        open={replacing}
        onClose={() => setReplacing(false)}
        replaceVideoId={video.id}
        onDone={(next) => {
          setReplacing(false);
          onReplaced(next);
        }}
      />
    </Flex>
  );
}
