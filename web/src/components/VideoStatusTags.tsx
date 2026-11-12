"use client";

import { Flex, theme } from "antd";
import type { VideoRow } from "@/lib/api";
import StatusText from "@/components/StatusText";
import { videoStatusTone } from "@/lib/videoStatus";

/** A video's status as a dot and a word, with its warnings after it in words. `only`: the status alone, or the
 * other labels alone (beside a card's title, when the status is said elsewhere). */
export default function VideoStatusTags({ video, only }: { video: VideoRow; only?: "status" | "labels" }) {
  const { token } = theme.useToken();
  const status = (
    <StatusText tone={videoStatusTone(video)} data-testid="video-status">
      {video.status_label}
    </StatusText>
  );
  if (only === "status") {
    return status;
  }
  const notes = [video.rerender_failed && "Render lại lỗi", video.mp4_outdated && "MP4 chưa cập nhật theo bản sửa"];
  return (
    <Flex vertical gap={2} style={{ fontSize: 13 }}>
      {only !== "labels" && status}
      {notes.filter(Boolean).map((note) => (
        <span key={String(note)} style={{ color: token.colorWarningText, fontSize: 12 }}>
          {note}
        </span>
      ))}
    </Flex>
  );
}
