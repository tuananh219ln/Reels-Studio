"use client";

import FormDrawer from "@/components/FormDrawer";
import { LOGO_POSITIONS } from "@/components/article/ArticleImages";
import { api, errorMessage, upload, type BrandDetail, type LogoPosition, type PhotoLogo } from "@/lib/api";
import { DeleteOutlined } from "@ant-design/icons";
import { App, Button, ColorPicker, Flex, Radio, Slider, Spin, Switch, Typography } from "antd";
import { useEffect, useState } from "react";

const DEFAULTS: PhotoLogo = { position: "bottom_right", size: 12, margin: 3, opacity: 1,
  alt_threshold: null,
  shape: "circle",
  border: true,
  border_color: "#FFFFFF",
  shadow: true,
};
const DEFAULT_THRESHOLD = 0.35;
const SAMPLES = [
  { ratio: "1:1", label: "1:1 · 1080×1080" },
  { ratio: "4:5", label: "4:5 · 1080×1350" },
  { ratio: "1.91:1", label: "1.91:1 · 1200×628" },
];

/** The address of a sample photo drawn by the api with the settings on screen, saved or not. */
function sampleUrl(brandId: number, ratio: string, look: PhotoLogo, version: string): string {
  const params = new URLSearchParams({
    ratio,
    position: look.position,
    size: String(look.size),
    margin: String(look.margin),
    opacity: String(look.opacity),
    shape: look.shape,
    border: String(look.border),
    border_color: look.border_color,
    shadow: String(look.shadow),
    v: version,
  });
  if (look.alt_threshold === null) params.set("no_alt", "true");
  else params.set("alt_threshold", String(look.alt_threshold));
  return `/api/brands/${brandId}/photo-sample?${params.toString()}`;
}

/**
 * "Logo trên ảnh bài viết" of a Page: where its logo sits on every article photo posted to it (one of nine places),
 * how wide, how far in and how opaque, and a white logo for dark photos. The three samples are drawn by the api with
 * the same code that lays the logo on a posted photo. Only the brand's owner changes it.
 */
export default function PhotoLogoDrawer({ brandId, onClose }: { brandId: number; onClose: () => void }) {
  const { message } = App.useApp();
  const [brand, setBrand] = useState<BrandDetail | null>(null);
  const [look, setLook] = useState<PhotoLogo>(DEFAULTS);
  // What the samples show: the settings once the member stops dragging for a moment.
  const [shown, setShown] = useState<PhotoLogo>(DEFAULTS);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<BrandDetail>(`/brands/${brandId}`)
      .then((loaded) => {
        setBrand(loaded);
        setLook(loaded.photo_logo);
        setShown(loaded.photo_logo);
      })
      .catch((err) => message.error(errorMessage(err)));
  }, [brandId, message]);

  useEffect(() => {
    const timer = setTimeout(() => setShown(look), 300);
    return () => clearTimeout(timer);
  }, [look]);

  const readOnly = brand !== null && !brand.mine;
  const change = (fields: Partial<PhotoLogo>) => setLook((current) => ({ ...current, ...fields }));

  async function save() {
    setSaving(true);
    try {
      const saved = await api<BrandDetail>(`/brands/${brandId}`, "PATCH", {
        photo_logo_position: look.position,
        photo_logo_size: look.size,
        photo_logo_margin: look.margin,
        photo_logo_opacity: look.opacity,
        photo_logo_alt_threshold: look.alt_threshold,
        photo_logo_shape: look.shape,
        photo_logo_border: look.border,
        photo_logo_border_color: look.border_color,
        photo_logo_shadow: look.shadow,
      });
      setBrand(saved);
      message.success("Đã lưu logo trên ảnh");
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function altLogo(work: () => Promise<Pick<BrandDetail, "logo_alt_url">>) {
    setBusy(true);
    try {
      const result = await work();
      setBrand((current) => (current ? { ...current, logo_alt_url: result.logo_alt_url } : current));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const version = brand ? `${brand.logo_url ?? ""}${brand.logo_alt_url ?? ""}` : "";

  return (
    <FormDrawer
      title={brand ? `Logo trên ảnh bài viết · ${brand.name}` : "Logo trên ảnh bài viết"}
      open
      width={760}
      onClose={onClose}
      onOk={save}
      okText="Lưu"
      confirmLoading={saving}
      okButtonProps={{ disabled: !brand || readOnly }}
    >
      {!brand ? (
        <Spin />
      ) : (
        <Flex gap={24} wrap data-testid="photo-logo-drawer">
          <Flex vertical gap={14} style={{ flex: "1 1 260px" }}>
            <Typography.Text type="secondary">
              Áp dụng cho mọi ảnh bài viết đăng lên Page này. Có thể tắt hoặc đổi vị trí riêng từng ảnh khi tạo bài.
            </Typography.Text>
            {readOnly && (
              <Typography.Text type="warning">Chỉ chủ Page ({brand.owner_name}) sửa được phần này.</Typography.Text>
            )}
            <Flex gap={10} align="center">
              {brand.logo_url && (
                // eslint-disable-next-line @next/next/no-img-element -- the logo served by the api
                <img src={brand.logo_url} alt="Logo chính" width={56} height={56} style={{ objectFit: "contain" }} />
              )}
              <Typography.Text>Logo chính (đổi ở thẻ Page)</Typography.Text>
            </Flex>
            <Flex gap={10} align="center" wrap>
              {brand.logo_alt_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- the white logo served by the api
                <img
                  src={brand.logo_alt_url}
                  alt="Logo phụ"
                  width={56}
                  height={56}
                  style={{ objectFit: "contain", background: "#222", borderRadius: 6 }}
                />
              ) : null}
              <Flex vertical>
                <Typography.Text>Logo phụ (bản trắng)</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Tự dùng khi nền chỗ đặt logo tối
                </Typography.Text>
              </Flex>
              <label>
                <input
                  type="file"
                  accept="image/png,image/webp,image/jpeg"
                  hidden
                  aria-label="Tải logo phụ"
                  disabled={readOnly || busy}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void altLogo(() => upload<BrandDetail>(`/brands/${brandId}/logo-alt`, file));
                  }}
                />
                <Button
                  size="small"
                  loading={busy}
                  disabled={readOnly}
                  onClick={(event) => event.currentTarget.parentElement?.querySelector("input")?.click()}
                >
                  {brand.logo_alt_url ? "Đổi" : "Tải lên"}
                </Button>
              </label>
              {brand.logo_alt_url && (
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label="Xoá logo phụ"
                  disabled={readOnly || busy}
                  onClick={() => void altLogo(() => api<BrandDetail>(`/brands/${brandId}/logo-alt`, "DELETE"))}
                />
              )}
            </Flex>
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                KIỂU LOGO
              </Typography.Text>
              <div style={{ marginTop: 6 }}>
                <Radio.Group
                  aria-label="Kiểu logo"
                  value={look.shape}
                  disabled={readOnly}
                  optionType="button"
                  onChange={(event) => change({ shape: event.target.value })}
                  options={[
                    { value: "circle", label: "Tròn" },
                    { value: "rounded", label: "Vuông bo góc" },
                    { value: "none", label: "Giữ nguyên" },
                  ]}
                />
              </div>
            </div>
            {look.shape !== "none" && (
              <Flex gap={16} align="center" wrap>
                <Flex gap={8} align="center">
                  <Switch
                    size="small"
                    checked={look.border}
                    disabled={readOnly}
                    aria-label="Viền quanh logo"
                    onChange={(on) => change({ border: on })}
                  />
                  <Typography.Text>Viền</Typography.Text>
                  {look.border && (
                    <ColorPicker
                      size="small"
                      value={look.border_color}
                      disabled={readOnly}
                      disabledAlpha
                      aria-label="Màu viền"
                      onChangeComplete={(color) => change({ border_color: color.toHexString().toUpperCase() })}
                    />
                  )}
                </Flex>
                <Flex gap={8} align="center">
                  <Switch
                    size="small"
                    checked={look.shadow}
                    disabled={readOnly}
                    aria-label="Bóng mờ dưới logo"
                    onChange={(on) => change({ shadow: on })}
                  />
                  <Typography.Text>Bóng mờ</Typography.Text>
                </Flex>
              </Flex>
            )}
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                VỊ TRÍ
              </Typography.Text>
              <div
                role="radiogroup"
                aria-label="Vị trí logo"
                style={{ display: "grid", gridTemplateColumns: "repeat(3, 36px)", gap: 6, marginTop: 6 }}
              >
                {LOGO_POSITIONS.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    role="radio"
                    aria-checked={look.position === item.value}
                    aria-label={item.label}
                    title={item.label}
                    disabled={readOnly}
                    onClick={() => change({ position: item.value as LogoPosition })}
                    style={{
                      width: 36,
                      height: 28,
                      borderRadius: 6,
                      cursor: readOnly ? "default" : "pointer",
                      border: "1px solid var(--ant-color-border)",
                      background: look.position === item.value ? "var(--ant-color-primary)" : "transparent",
                    }}
                  />
                ))}
              </div>
            </div>
            <label>
              <Flex justify="space-between">
                <Typography.Text>Kích thước</Typography.Text>
                <Typography.Text strong>{look.size}% cạnh ngắn</Typography.Text>
              </Flex>
              <Slider
                aria-label="Kích thước logo"
                min={3}
                max={40}
                value={look.size}
                disabled={readOnly}
                onChange={(value) => change({ size: value })}
              />
            </label>
            <label>
              <Flex justify="space-between">
                <Typography.Text>Lề</Typography.Text>
                <Typography.Text strong>{look.margin}%</Typography.Text>
              </Flex>
              <Slider
                aria-label="Lề logo"
                min={0}
                max={20}
                value={look.margin}
                disabled={readOnly}
                onChange={(value) => change({ margin: value })}
              />
            </label>
            <label>
              <Flex justify="space-between">
                <Typography.Text>Độ mờ</Typography.Text>
                <Typography.Text strong>{Math.round(look.opacity * 100)}%</Typography.Text>
              </Flex>
              <Slider
                aria-label="Độ mờ logo"
                min={10}
                max={100}
                value={Math.round(look.opacity * 100)}
                disabled={readOnly}
                onChange={(value) => change({ opacity: value / 100 })}
              />
            </label>
            <Flex gap={8} align="center">
              <Switch
                size="small"
                checked={look.alt_threshold !== null}
                disabled={readOnly || !brand.logo_alt_url}
                aria-label="Tự đổi logo trắng trên nền tối"
                onChange={(on) => change({ alt_threshold: on ? DEFAULT_THRESHOLD : null })}
              />
              <Typography.Text>Tự đổi logo trắng trên nền tối</Typography.Text>
            </Flex>
            {look.alt_threshold !== null && (
              <label>
                <Flex justify="space-between">
                  <Typography.Text type="secondary">Nền tối hơn</Typography.Text>
                  <Typography.Text strong>{Math.round(look.alt_threshold * 100)}% độ sáng</Typography.Text>
                </Flex>
                <Slider
                  aria-label="Ngưỡng độ sáng"
                  min={5}
                  max={90}
                  value={Math.round(look.alt_threshold * 100)}
                  disabled={readOnly}
                  onChange={(value) => change({ alt_threshold: value / 100 })}
                />
              </label>
            )}
            <Button disabled={readOnly} onClick={() => setLook(DEFAULTS)} style={{ alignSelf: "start" }}>
              Khôi phục mặc định
            </Button>
          </Flex>
          <Flex vertical gap={8} style={{ flex: "1 1 300px" }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              XEM TRƯỚC TRÊN 3 TỈ LỆ
            </Typography.Text>
            {brand.logo_url ? (
              <Flex gap={8} wrap align="end" data-testid="photo-logo-samples">
                {SAMPLES.map((sample) => (
                  <Flex key={sample.ratio} vertical gap={4} style={{ flex: "1 1 120px" }}>
                    {/* eslint-disable-next-line @next/next/no-img-element -- drawn by the api, same as a posted photo */}
                    <img
                      src={sampleUrl(brandId, sample.ratio, shown, version)}
                      alt={`Mẫu ${sample.ratio}`}
                      style={{ width: "100%", borderRadius: 6, display: "block" }}
                    />
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {sample.label}
                    </Typography.Text>
                  </Flex>
                ))}
              </Flex>
            ) : (
              <Typography.Text type="secondary">Page chưa có logo: tải logo ở thẻ Page trước.</Typography.Text>
            )}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Logo cách mép {look.margin}% và rộng {look.size}% cạnh ngắn ảnh, nên tỉ lệ giữ đúng trên mọi kích thước.
            </Typography.Text>
          </Flex>
        </Flex>
      )}
    </FormDrawer>
  );
}
