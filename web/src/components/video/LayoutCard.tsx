"use client";

import { Card, Flex, Segmented, Typography } from "antd";
import type { VideoDetail, VideoOptions } from "@/lib/api";

const HINTS: Record<VideoOptions["layout_profile"], string> = {
  balanced: "Đăng bài thường lên TikTok, Facebook Reels: phụ đề nằm thấp.",
  universal: "Đăng cả YouTube Shorts, Instagram Reels hoặc chạy quảng cáo: phụ đề cao hơn, lề phải rộng hơn.",
};

/** "Vùng an toàn" on a video's Thiết lập tab: which apps' edges the text, the captions and the logo keep clear of. */
export default function LayoutCard({
  video,
  disabled,
  onSave,
}: {
  video: VideoDetail;
  disabled: boolean;
  onSave: (options: Pick<VideoOptions, "layout_profile">) => void;
}) {
  const profile = video.layout.profile;
  return (
    <Card size="small" data-testid="layout-settings">
      <Flex vertical gap={6}>
        <Flex gap={8} align="center" justify="space-between" wrap>
          <Typography.Text strong>Vùng an toàn</Typography.Text>
          <Segmented
            size="small"
            aria-label="Vùng an toàn"
            value={profile}
            disabled={disabled}
            options={[
              { value: "balanced", label: "TikTok, Facebook" },
              { value: "universal", label: "Mọi nền tảng" },
            ]}
            onChange={(layout_profile) => onSave({ layout_profile: layout_profile as VideoOptions["layout_profile"] })}
          />
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {HINTS[profile]}
        </Typography.Text>
      </Flex>
    </Card>
  );
}
