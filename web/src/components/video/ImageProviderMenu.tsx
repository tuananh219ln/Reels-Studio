"use client";

import { DownOutlined } from "@ant-design/icons";
import { Button, Dropdown } from "antd";
import { useState } from "react";
import { api } from "@/lib/api";

export type ImageProviders = {
  default: "cloudflare" | "gemini";
  providers: { id: "cloudflare" | "gemini"; label: string; configured: boolean }[];
};

const NOTES = { cloudflare: "miễn phí khoảng 57 ảnh/ngày", gemini: "tốn phí" } as const;

/**
 * The arrow beside a "Tạo ảnh AI" button: makes the photos with a provider chosen for this press. The button itself
 * uses the team's default (Cài đặt › Nguồn tư liệu); the menu is how a member moves to Gemini when Cloudflare's
 * free photos for the day are used up, since the app never switches to a paid provider by itself.
 */
export default function ImageProviderMenu({
  disabled,
  onPick,
}: {
  disabled: boolean;
  onPick: (provider: "cloudflare" | "gemini") => void;
}) {
  const [offered, setOffered] = useState<ImageProviders | null>(null);

  async function load() {
    try {
      setOffered(await api<ImageProviders>("/settings/image-providers"));
    } catch {
      setOffered(null);
    }
  }

  return (
    <Dropdown
      trigger={["click"]}
      disabled={disabled}
      onOpenChange={(open) => open && void load()}
      menu={{
        items: (offered?.providers ?? []).map((item) => ({
          key: item.id,
          disabled: !item.configured,
          label: `Tạo bằng ${item.label}${item.id === offered?.default ? " (mặc định)" : ""} · ${
            item.configured ? NOTES[item.id] : "chưa có key"
          }`,
        })),
        onClick: ({ key }) => onPick(key as "cloudflare" | "gemini"),
      }}
    >
      <Button aria-label="Chọn nguồn ảnh AI" icon={<DownOutlined />} disabled={disabled} />
    </Dropdown>
  );
}
