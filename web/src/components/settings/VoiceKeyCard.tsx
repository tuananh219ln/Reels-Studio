"use client";

import Link from "next/link";
import { App, Button, Card, Flex, Input, Popconfirm, Space, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import StatusText from "@/components/StatusText";
import { forgetVoices } from "@/components/video/VideoSettings";
import { api, errorMessage } from "@/lib/api";

/** What GET /settings/sources says of a voice service's key: where it comes from and its last characters, never the
 * key. */
type VoiceKey = {
  configured: boolean;
  key: { origin: "saved" | "unreadable" | "env" | null; hint: string; signup_url: string };
};

/** The narration services whose key is pasted on Cài đặt › Mô hình AI, by their api source_keys name. */
export const VOICE_KEY_SERVICES = {
  vieneu: {
    name: "VieNeu",
    title: "Giọng đọc VieNeu",
    about: "Giọng tiếng Việt của VieNeu cho lời đọc từng cảnh.",
    billing: "tính phí theo tài khoản VieNeu",
    signup: "Tạo key ở trang Nhà phát triển của VieNeu",
    placeholder: "Dán API key (vn_sk_…) vào đây…",
    note: "",
  },
  google_tts: {
    name: "Google",
    title: "Giọng đọc Google",
    about:
      "Giọng tiếng Việt của Google Cloud Text-to-Speech (Standard, WaveNet, Neural2, Chirp3-HD) cho lời đọc từng cảnh.",
    billing: "tính phí theo dự án Google Cloud (Chirp3-HD đắt nhất, Standard rẻ nhất)",
    signup: "Tạo API key ở Google Cloud Console",
    placeholder: "Dán API key (AIza…) vào đây…",
    note: "Dự án của key cần bật thanh toán (billing) và Cloud Text-to-Speech API; nên giới hạn key chỉ gọi API này.",
  },
} as const;

export type VoiceKeyService = keyof typeof VOICE_KEY_SERVICES;

/** A voice service's key card on Cài đặt › Mô hình AI: paste, replace or remove its API key. Its voices then join the
 * "Giọng" picker of Thiết lập mặc định and of each video. Stored like the other keys (api source_keys.py).
 * `footer`: shown under the card's text (the "Sửa lần cuối" line); `onSaved` after a key is saved or removed. */
export default function VoiceKeyCard({
  service,
  footer,
  onSaved,
}: {
  service: VoiceKeyService;
  footer?: React.ReactNode;
  onSaved?: () => void;
}) {
  const { message } = App.useApp();
  const text = VOICE_KEY_SERVICES[service];
  const [state, setState] = useState<VoiceKey | null>(null);
  const [pasting, setPasting] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  const show = useCallback(
    (data: Partial<Record<VoiceKeyService, VoiceKey>>) => {
      const found = data[service] ?? null;
      setState(found);
      setPasting(!found?.key.origin || found.key.origin === "unreadable");
    },
    [service],
  );

  useEffect(() => {
    api<Partial<Record<VoiceKeyService, VoiceKey>>>("/settings/sources")
      .then(show)
      .catch((err) => message.error(errorMessage(err)));
  }, [message, show]);

  async function save(apiKey: string) {
    setBusy(true);
    try {
      show(
        await api<Partial<Record<VoiceKeyService, VoiceKey>>>(`/settings/sources/${service}/key`, "PUT", {
          api_key: apiKey,
        }),
      );
      setKey("");
      forgetVoices();
      onSaved?.();
      message.success(apiKey ? `Đã lưu API key của ${text.name}` : `Đã xoá API key của ${text.name}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!state) {
    return null;
  }
  const origin = state.key.origin;
  return (
    <Card
      size="small"
      data-testid={`${service}-key`}
      title={
        <Flex wrap gap={8} align="center">
          <span>{text.title}</span>
          {state.configured ? (
            <StatusText tone="done">Sẵn sàng</StatusText>
          ) : (
            <StatusText tone="idle">Chưa cấu hình</StatusText>
          )}
        </Flex>
      }
    >
      <Flex vertical gap={10}>
        <Typography.Text type="secondary">
          {text.about} Có key thì các giọng {text.name} hiện trong ô “Giọng” ở Thiết lập mặc định và ở Thiết lập của
          từng video; mỗi cảnh đọc một lần, {text.billing}.{" "}
          <a href={state.key.signup_url} target="_blank" rel="noreferrer">
            {text.signup}
          </a>
          .{text.note && ` ${text.note}`} Key giọng ElevenLabs ở{" "}
          <Link prefetch={false} href="/settings/sources">
            Cài đặt › Nguồn tư liệu
          </Link>
          .
        </Typography.Text>
        {origin === "unreadable" && (
          <Typography.Text type="warning">
            Không đọc được key đã lưu (khoá mã hoá trong thư mục lưu trữ đã đổi). Hãy dán lại key.
          </Typography.Text>
        )}
        {!pasting ? (
          <Flex wrap gap={8} align="center">
            <Typography.Text data-testid="key-status">
              {origin === "saved"
                ? `Đã lưu${state.key.hint ? `, kết thúc bằng …${state.key.hint}` : ""}`
                : "Đang dùng key trong file .env của máy chủ"}
            </Typography.Text>
            <Button size="small" onClick={() => setPasting(true)}>
              Dán key mới
            </Button>
            {origin === "saved" && (
              <Popconfirm
                title={`Xoá API key của ${text.name}?`}
                okText="Xoá"
                cancelText="Huỷ"
                okButtonProps={{ danger: true }}
                onConfirm={() => save("")}
              >
                <Button size="small" danger loading={busy}>
                  Xoá key
                </Button>
              </Popconfirm>
            )}
          </Flex>
        ) : (
          <Space.Compact style={{ width: "100%" }}>
            <Input.Password
              aria-label={`API key ${text.name}`}
              value={key}
              autoComplete="new-password"
              placeholder={text.placeholder}
              onChange={(event) => setKey(event.target.value)}
              onPressEnter={() => key.trim() && void save(key)}
            />
            <Button type="primary" disabled={!key.trim()} loading={busy} onClick={() => save(key)}>
              Lưu key
            </Button>
            {origin !== null && origin !== "unreadable" && (
              <Button onClick={() => (setPasting(false), setKey(""))}>Huỷ</Button>
            )}
          </Space.Compact>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Key được mã hoá khi lưu và không bao giờ hiện lại.
        </Typography.Text>
      </Flex>
      {footer}
    </Card>
  );
}
