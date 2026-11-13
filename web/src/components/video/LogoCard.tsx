"use client";

import { ArrowRightOutlined } from "@ant-design/icons";
import { Card, Flex, Select, Switch, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { COLORS } from "@/app/theme";
import StatusText from "@/components/StatusText";
import { api, type BrandRow, type VideoDetail } from "@/lib/api";

// Where the render lays the badge on a content scene (docs/decisions/2026-11-13-brand-logo.md): x 888–1020 and
// y 200–332 of 1080×1920, as shares of the small 9:16 frame.
const BADGE = { left: "82.2%", top: "10.4%", width: "12.2%" } as const;
const FRAME_WIDTH = 76;

/**
 * "Logo", first on a video's Thiết lập tab and always open: the channel, whether its logo is laid on the MP4, and a
 * small 9:16 frame showing where it goes. The logo sits in the platforms' safe zone, so one file serves Facebook,
 * TikTok and YouTube. A posted video keeps its channel.
 */
export default function LogoCard({
  video,
  disabled,
  previewUrl,
  onSave,
}: {
  video: VideoDetail;
  disabled: boolean;
  /** A content scene's picture, under the badge in the small frame. */
  previewUrl: string | null;
  onSave: (options: { brand_id?: number | null; logo_enabled?: boolean }) => void;
}) {
  const [brands, setBrands] = useState<BrandRow[]>([]);
  useEffect(() => {
    api<BrandRow[]>("/brands")
      .then(setBrands)
      .catch(() => setBrands([]));
  }, []);
  const posted = video.post_stage === "posted";
  const current = brands.find((brand) => brand.id === video.brand?.id);
  const badge = video.brand?.logo_badge_url ?? null;
  const on = video.logo_enabled && Boolean(badge);
  // A member picks among their own channels; the video's own stays in the list even when a teammate's.
  const options = brands
    .filter((brand) => brand.mine || brand.id === video.brand?.id)
    .map((brand) => ({
      value: brand.id,
      label: (
        <Flex gap={8} align="center">
          {brand.logo_badge_url && (
            // eslint-disable-next-line @next/next/no-img-element -- a small badge served by the api
            <img src={brand.logo_badge_url} alt="" width={20} height={20} />
          )}
          {brand.name}
        </Flex>
      ),
    }));
  return (
    <Card
      size="small"
      data-testid="logo-settings"
      title="Logo"
      extra={on ? <StatusText tone="success">Đang gắn</StatusText> : <StatusText tone="idle">Chưa gắn</StatusText>}
      // A light brand tint: the one group always open, at the top of the tab.
      style={{ background: COLORS.primaryBg, borderColor: COLORS.primaryBorder }}
      styles={{ header: { borderBottom: "none", minHeight: 40 }, body: { paddingTop: 0 } }}
    >
      <Flex gap={12} align="flex-start">
        <Flex vertical gap={10} style={{ flex: 1, minWidth: 0 }}>
          <Flex gap={8} align="center">
            <Typography.Text type="secondary" style={{ width: 40, flex: "none", fontSize: 13 }}>
              Kênh
            </Typography.Text>
            <Select
              aria-label="Kênh của video"
              placeholder="Chưa chọn kênh"
              allowClear
              style={{ flex: 1, minWidth: 0 }}
              disabled={disabled || posted}
              value={video.brand?.id ?? null}
              options={options}
              onChange={(brandId: number | undefined) => onSave({ brand_id: brandId ?? null })}
              notFoundContent={
                <Typography.Text type="secondary">Chưa có kênh: thêm logo ở Quản lý Page</Typography.Text>
              }
            />
          </Flex>
          <Flex gap={8} align="center">
            <Typography.Text type="secondary" style={{ width: 40, flex: "none", fontSize: 13 }}>
              Gắn
            </Typography.Text>
            <Switch
              aria-label="Gắn logo vào video"
              checked={video.logo_enabled}
              disabled={disabled || !badge}
              onChange={(logo_enabled) => onSave({ logo_enabled })}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {video.brand ? "Góc trên phải, trừ cảnh tiêu đề" : "Chọn kênh để gắn logo"}
            </Typography.Text>
          </Flex>
          {posted && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Video đã đăng nên không đổi kênh được: hãy tạo bản cho kênh khác.
            </Typography.Text>
          )}
          {video.brand && !badge && current && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Kênh “{video.brand.name}” chưa có logo.{" "}
              <Link prefetch={false} href="/fanpages">
                Thêm logo cho kênh
              </Link>
            </Typography.Text>
          )}
          <Link prefetch={false} href="/fanpages" style={{ fontSize: 13 }}>
            Quản lý Page <ArrowRightOutlined style={{ fontSize: 11 }} />
          </Link>
        </Flex>
        <LogoFrame previewUrl={previewUrl} badge={on ? badge : null} />
      </Flex>
    </Card>
  );
}

/** A small 9:16 frame of a content scene with the badge where the render puts it; empty grey without a picture. */
function LogoFrame({ previewUrl, badge }: { previewUrl: string | null; badge: string | null }) {
  return (
    <div
      data-testid="logo-frame"
      aria-hidden
      style={{
        position: "relative",
        flex: "none",
        width: FRAME_WIDTH,
        aspectRatio: "9 / 16",
        borderRadius: 6,
        overflow: "hidden",
        background: COLORS.muted,
        border: `1px solid ${COLORS.border}`,
      }}
    >
      {previewUrl && (
        // eslint-disable-next-line @next/next/no-img-element -- the api draws the preview; next/image adds nothing
        <img src={previewUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
      )}
      {badge && (
        // eslint-disable-next-line @next/next/no-img-element -- a small badge served by the api
        <img src={badge} alt="" style={{ position: "absolute", ...BADGE, aspectRatio: "1", borderRadius: "50%" }} />
      )}
    </div>
  );
}
