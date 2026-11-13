"use client";

import { Button, Card, Flex, Select, Switch, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type BrandRow, type VideoDetail } from "@/lib/api";

/**
 * "Logo" on a video's Thiết lập tab: the channel and whether its logo is laid on the MP4. The logo goes in the
 * platforms' safe zone, so one file serves Facebook, TikTok and YouTube. A posted video keeps its channel.
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
  const hasLogo = Boolean(video.brand?.logo_badge_url);
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
    <Card title="Logo" size="small" data-testid="logo-settings">
      <Flex vertical gap={12}>
        <Flex vertical gap={4}>
          <Typography.Text>Kênh</Typography.Text>
          <Select
            aria-label="Kênh của video"
            placeholder="Chưa chọn kênh"
            allowClear
            disabled={disabled || posted}
            value={video.brand?.id ?? null}
            options={options}
            onChange={(brandId: number | undefined) => onSave({ brand_id: brandId ?? null })}
            notFoundContent={<Typography.Text type="secondary">Chưa có kênh: thêm logo ở Quản lý Page</Typography.Text>}
          />
          {posted && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Video đã đăng nên không đổi kênh được: hãy tạo bản cho kênh khác.
            </Typography.Text>
          )}
        </Flex>
        <Flex gap={8} align="center">
          <Switch
            aria-label="Gắn logo vào video"
            checked={video.logo_enabled}
            disabled={disabled || !hasLogo}
            onChange={(logo_enabled) => onSave({ logo_enabled })}
          />
          <Typography.Text type={hasLogo ? undefined : "secondary"}>Gắn logo vào video</Typography.Text>
        </Flex>
        {video.brand && !hasLogo && current && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Kênh “{video.brand.name}” chưa có logo.{" "}
            <Link prefetch={false} href="/fanpages">
              Thêm logo cho kênh
            </Link>
          </Typography.Text>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Cảnh tiêu đề: logo giữa, trên hộp chữ. Các cảnh sau: góc trên bên phải.
        </Typography.Text>
        {!video.brand && (
          <Button size="small" type="link" style={{ padding: 0, alignSelf: "flex-start" }} href="/fanpages">
            Quản lý Page
          </Button>
        )}
      </Flex>
    </Card>
  );
}
