"use client";

import { CheckCircleFilled, SendOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Skeleton, Switch, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import GuideButton from "@/components/GuideButton";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { api, errorMessage, formatDateTime } from "@/lib/api";

type Status = {
  configured: boolean;
  linked: boolean;
  username: string | null;
  linked_at: string | null;
  muted: string[];
  kinds: { key: string; label: string }[];
};

/** Cài đặt › Thông báo Telegram: the member links their own chat with the team's bot, which then tells them, privately,
 * about their own work (api telegram.py, docs/decisions/2026-11-26-telegram-private.md). */
export default function TelegramSettingsPage() {
  const { message } = App.useApp();
  const [status, setStatus] = useState<Status | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(
    () =>
      api<Status>("/telegram").then(setStatus, (err) => {
        message.error(errorMessage(err));
      }),
    [message],
  );

  useEffect(() => {
    load();
  }, [load]);

  // While the bot's link is open in Telegram, look every few seconds whether /start has linked the chat.
  const waiting = link !== null && status !== null && !status.linked;
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => {
      api<Status>("/telegram").then(setStatus, () => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [waiting]);

  async function run<T>(name: string, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(name);
    try {
      return await action();
    } catch (err) {
      message.error(errorMessage(err));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function connect() {
    const answer = await run("link", () => api<{ url: string }>("/telegram/link", "POST"));
    if (!answer) return;
    setLink(answer.url);
    window.open(answer.url, "_blank", "noopener");
  }

  async function unlink() {
    const answer = await run("unlink", () => api<Status>("/telegram/link", "DELETE"));
    if (answer) {
      setStatus(answer);
      setLink(null);
      message.success("Đã ngắt kết nối Telegram");
    }
  }

  async function sendTest() {
    if (await run("test", () => api("/telegram/test", "POST"))) message.success("Đã gửi tin thử, mở Telegram để xem");
  }

  async function toggle(kind: string, on: boolean) {
    if (!status) return;
    const muted = on ? status.muted.filter((one) => one !== kind) : [...status.muted, kind];
    const answer = await run(kind, () => api<Status>("/telegram/muted", "PUT", { muted }));
    if (answer) setStatus(answer);
  }

  return (
    <>
      <SettingsHeader
        title="Thông báo Telegram"
        description="Bot Telegram của nhóm nhắn riêng cho bạn về việc của chính bạn, trong đoạn chat riêng giữa bạn và bot. Nhóm chat chung chỉ nhận tin chung của cả đội."
        actions={<GuideButton screen="telegram" />}
      />
      {!status ? (
        <Card size="small" style={{ maxWidth: 640 }}>
          <Skeleton active paragraph={{ rows: 3 }} />
        </Card>
      ) : !status.configured ? (
        <Alert
          type="info"
          showIcon
          style={{ maxWidth: 640 }}
          title="Bot Telegram chưa bật"
          description="Người quản lý cần thêm token của bot (TELEGRAM_BOT_TOKEN) cho máy chủ. Khi bật xong, trang này hiện nút Kết nối Telegram."
        />
      ) : (
        <Flex vertical gap={16} style={{ maxWidth: 640 }}>
          <Card size="small" title="Kết nối">
            {status.linked ? (
              <Flex vertical gap={12}>
                <Typography.Text>
                  <CheckCircleFilled style={{ color: "var(--ant-color-success)", marginRight: 8 }} />
                  Đã kết nối{status.username ? ` với Telegram @${status.username}` : ""}
                  {status.linked_at ? ` từ ${formatDateTime(status.linked_at)}` : ""}
                </Typography.Text>
                <Flex gap={8} wrap>
                  <Button icon={<SendOutlined />} loading={busy === "test"} onClick={sendTest}>
                    Gửi tin thử
                  </Button>
                  <Button danger loading={busy === "unlink"} onClick={unlink}>
                    Ngắt kết nối
                  </Button>
                </Flex>
              </Flex>
            ) : (
              <Flex vertical gap={12} align="flex-start">
                <Typography.Text type="secondary">
                  Bấm nút dưới đây, Telegram mở cuộc trò chuyện với bot, rồi bấm Start. Chỉ làm một lần.
                </Typography.Text>
                <Button type="primary" icon={<SendOutlined />} loading={busy === "link"} onClick={connect}>
                  Kết nối Telegram
                </Button>
                {link && (
                  <Typography.Text type="secondary">
                    Đang chờ bạn bấm Start trong Telegram. Telegram chưa mở?{" "}
                    <Typography.Link href={link} target="_blank" rel="noopener">
                      Mở link kết nối
                    </Typography.Link>{" "}
                    (dùng được 30 phút).
                  </Typography.Text>
                )}
              </Flex>
            )}
          </Card>
          <Card size="small" title="Nhận tin về">
            <Flex vertical gap={12}>
              {status.kinds.map((kind) => (
                <Flex key={kind.key} gap={12} align="center" justify="space-between">
                  <Typography.Text>{kind.label}</Typography.Text>
                  <Switch
                    aria-label={kind.label}
                    checked={!status.muted.includes(kind.key)}
                    loading={busy === kind.key}
                    onChange={(on) => toggle(kind.key, on)}
                  />
                </Flex>
              ))}
            </Flex>
          </Card>
        </Flex>
      )}
    </>
  );
}
