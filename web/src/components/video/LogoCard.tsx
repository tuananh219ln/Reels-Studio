"use client";

import { ArrowRightOutlined } from "@ant-design/icons";
import { Card, Flex, Select, Switch, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { COLORS } from "@/app/theme";
import StatusText from "@/components/StatusText";
import { api, type BrandRow, type VideoDetail } from "@/lib/api";

/**
 * "Logo", first on a video's Thiết lập tab, in two rows: the switch with where the logo goes and whether it is on,
 * then the channel with "Quản lý kênh". The logo sits in the platforms' safe zone, so one file serves Facebook,
 * TikTok and YouTube (docs/decisions/2026-11-13-brand-logo.md). A posted video keeps its channel.
 */
export default function LogoCard({
  video,
  disabled,
  onSave,
}: {
  video: VideoDetail;
  disabled: boolean;
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
      className="logo-card"
      data-testid="logo-settings"
      // A light brand tint: the one group always open, at the top of the tab.
      style={{ background: COLORS.primaryBg, borderColor: COLORS.primaryBorder }}
    >
      <Flex vertical gap={8}>
        <div className="logo-card__row">
          <Typography.Text strong style={{ flex: "none" }}>
            Logo
          </Typography.Text>
          <Switch
            size="small"
            aria-label="Gắn logo vào video"
            checked={video.logo_enabled}
            disabled={disabled || !badge}
            onChange={(logo_enabled) => onSave({ logo_enabled })}
          />
          <Typography.Text type="secondary" ellipsis style={{ fontSize: 12, minWidth: 0 }}>
            {video.brand ? "Góc trên phải, trừ cảnh tiêu đề" : "Chọn kênh để gắn logo"}
          </Typography.Text>
          <span style={{ marginLeft: "auto", flex: "none" }}>
            {on ? <StatusText tone="success">Đang gắn</StatusText> : <StatusText tone="idle">Chưa gắn</StatusText>}
          </span>
        </div>
        <div className="logo-card__row">
          <Typography.Text type="secondary" style={{ flex: "none", fontSize: 13 }}>
            Kênh
          </Typography.Text>
          <Select
            aria-label="Kênh của video"
            placeholder="Chưa chọn kênh"
            allowClear
            disabled={disabled || posted}
            value={video.brand?.id ?? null}
            options={options}
            onChange={(brandId: number | undefined) => onSave({ brand_id: brandId ?? null })}
            notFoundContent={<Typography.Text type="secondary">Chưa có kênh: thêm logo ở Quản lý kênh</Typography.Text>}
          />
          <Link prefetch={false} href="/fanpages" style={{ fontSize: 13 }}>
            Quản lý kênh <ArrowRightOutlined style={{ fontSize: 11 }} />
          </Link>
        </div>
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
      </Flex>
    </Card>
  );
}
