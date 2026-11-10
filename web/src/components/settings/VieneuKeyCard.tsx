"use client";

import { App, Button, Card, Flex, Input, Popconfirm, Space, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import StatusText from "@/components/StatusText";
import { forgetVoices } from "@/components/video/VideoSettings";
import { api, errorMessage } from "@/lib/api";

/** What GET /settings/sources says of the VieNeu key: where it comes from and its last characters, never the key. */
type VieneuKey = {
  configured: boolean;
  key: { origin: "saved" | "unreadable" | "env" | null; hint: string; signup_url: string };
};

/** "Giọng đọc VieNeu" on Cài đặt › Mô hình AI: paste, replace or remove the VieNeu API key. Its voices then join the
 * "Giọng" picker of Thiết lập mặc định and of each video. Stored like the other keys (api source_keys.py). */
/** `footer`: shown under the card's text (the "Sửa lần cuối" line); `onSaved` after a key is saved or removed. */
export default function VieneuKeyCard({ footer, onSaved }: { footer?: React.ReactNode; onSaved?: () => void } = {}) {
  const { message } = App.useApp();
  const [state, setState] = useState<VieneuKey | null>(null);
  const [pasting, setPasting] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  const show = useCallback((data: { vieneu?: VieneuKey }) => {
    const vieneu = data.vieneu ?? null;
    setState(vieneu);
    setPasting(!vieneu?.key.origin || vieneu.key.origin === "unreadable");
  }, []);

  useEffect(() => {
    api<{ vieneu?: VieneuKey }>("/settings/sources")
      .then(show)
      .catch((err) => message.error(errorMessage(err)));
  }, [message, show]);

  async function save(apiKey: string) {
    setBusy(true);
    try {
      show(await api<{ vieneu?: VieneuKey }>("/settings/sources/vieneu/key", "PUT", { api_key: apiKey }));
      setKey("");
      forgetVoices();
      onSaved?.();
      message.success(apiKey ? "Đã lưu API key của VieNeu" : "Đã xoá API key của VieNeu");
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
      data-testid="vieneu-key"
      title={
        <Flex wrap gap={8} align="center">
          <span>Giọng đọc VieNeu</span>
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
          Giọng tiếng Việt của VieNeu cho lời đọc từng cảnh. Có key thì các giọng VieNeu hiện trong ô “Giọng” ở Thiết
          lập mặc định và ở Thiết lập của từng video; mỗi cảnh đọc một lần, tính phí theo tài khoản VieNeu.{" "}
          <a href={state.key.signup_url} target="_blank" rel="noreferrer">
            Tạo key ở trang Nhà phát triển của VieNeu
          </a>
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
                title="Xoá API key của VieNeu?"
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
              aria-label="API key VieNeu"
              value={key}
              autoComplete="new-password"
              placeholder="Dán API key (vn_sk_…) vào đây…"
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
