"use client";

import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, WarningFilled } from "@ant-design/icons";
import { App, Button, Flex, Input, Popconfirm, Space, Tooltip, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { forgetVoices } from "@/components/video/VideoSettings";
import { api, errorMessage, formatDateTime } from "@/lib/api";

export type KeyService = "elevenlabs" | "gemini" | "vieneu";
type KeyRow = {
  id: number;
  label: string;
  hint: string;
  readable: boolean;
  error: string | null;
  error_at: string | null;
};
type ServiceKeys = { main: { error: string; at: string } | null; keys: KeyRow[] };
type KeysPayload = { services: Record<KeyService, ServiceKeys> };

const SERVICE_NAMES: Record<KeyService, string> = { elevenlabs: "ElevenLabs", gemini: "Gemini", vieneu: "VieNeu" };

/** Why a narration last could not use a key, with when (Vietnam time); gone once the key reads again. */
function KeyError({ error, at, who }: { error: string; at: string | null; who: string }) {
  return (
    <Typography.Text type="danger" style={{ display: "block", fontSize: 12 }} data-testid="key-error">
      <WarningFilled /> {who} lỗi{at ? ` lúc ${formatDateTime(at)}` : ""}: {error}. Lời đọc đã tự chuyển sang key kế
      tiếp.
    </Typography.Text>
  );
}

/** The team's backup narration keys of one service (api routes_api_keys.py), tried in order after the main key above
 * once it is wrong or out of quota. Add, rename, move up or down, remove; a key only ever goes in, the list shows its
 * last characters, and a key a narration could not use says why on its own row (the main key's under it). */
export default function ApiKeyList({ service, onChanged }: { service: KeyService; onChanged?: () => void }) {
  const { message } = App.useApp();
  const [data, setData] = useState<ServiceKeys | null>(null);
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const name = SERVICE_NAMES[service];

  const show = useCallback((payload: KeysPayload) => setData(payload.services[service] ?? null), [service]);

  useEffect(() => {
    api<KeysPayload>("/api-keys")
      .then(show)
      .catch((err) => message.error(errorMessage(err)));
  }, [message, show]);

  async function send(run: () => Promise<KeysPayload>, done: string) {
    setBusy(true);
    try {
      show(await run());
      forgetVoices();
      onChanged?.();
      message.success(done);
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    const added = await send(
      () => api<KeysPayload>("/api-keys", "POST", { service, api_key: key, label }),
      `Đã thêm key ${name}`,
    );
    if (added) {
      setKey("");
      setLabel("");
    }
  }

  if (!data) {
    return null;
  }
  const rows = data.keys;
  return (
    <div data-testid={`key-list-${service}`}>
      {data.main && <KeyError error={data.main.error} at={data.main.at} who="Key chính" />}
      <Typography.Text strong style={{ display: "block", marginTop: data.main ? 8 : 0 }}>
        Key dự phòng
      </Typography.Text>
      <Typography.Text type="secondary" style={{ display: "block", fontSize: 12 }}>
        Khi key trên sai hoặc hết hạn mức (hết lượt trong ngày, hết ký tự), lời đọc tự chuyển sang các key này theo thứ
        tự.
      </Typography.Text>
      <Flex vertical gap={6} style={{ marginTop: 6 }}>
        {rows.map((row, index) => (
          <div key={row.id} data-testid="key-row">
            <Flex wrap gap={8} align="center">
              <Typography.Text
                type={row.error ? "danger" : undefined}
                editable={{
                  maxLength: 40,
                  tooltip: "Đổi tên",
                  onChange: (value) =>
                    value.trim() &&
                    value.trim() !== row.label &&
                    void send(
                      () => api<KeysPayload>(`/api-keys/${row.id}`, "PATCH", { label: value }),
                      "Đã đổi tên key",
                    ),
                }}
              >
                {row.label}
              </Typography.Text>
              <Typography.Text type="secondary">{row.hint ? `…${row.hint}` : "…"}</Typography.Text>
              {!row.readable && <Typography.Text type="warning">Không đọc được, hãy xoá rồi thêm lại</Typography.Text>}
              <Space size={4}>
                <Tooltip title="Lên">
                  <Button
                    size="small"
                    aria-label={`Đưa ${row.label} lên`}
                    icon={<ArrowUpOutlined />}
                    disabled={busy || index === 0}
                    onClick={() =>
                      send(() => api<KeysPayload>(`/api-keys/${row.id}`, "PATCH", { move: -1 }), "Đã đổi thứ tự")
                    }
                  />
                </Tooltip>
                <Tooltip title="Xuống">
                  <Button
                    size="small"
                    aria-label={`Đưa ${row.label} xuống`}
                    icon={<ArrowDownOutlined />}
                    disabled={busy || index === rows.length - 1}
                    onClick={() =>
                      send(() => api<KeysPayload>(`/api-keys/${row.id}`, "PATCH", { move: 1 }), "Đã đổi thứ tự")
                    }
                  />
                </Tooltip>
                <Popconfirm
                  title={`Xoá ${row.label}?`}
                  okText="Xoá"
                  cancelText="Huỷ"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => send(() => api<KeysPayload>(`/api-keys/${row.id}`, "DELETE"), "Đã xoá key")}
                >
                  <Button size="small" danger aria-label={`Xoá ${row.label}`} icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            </Flex>
            {row.error && <KeyError error={row.error} at={row.error_at} who="Key này" />}
          </div>
        ))}
        <Space.Compact style={{ width: "100%", maxWidth: 560 }}>
          <Input
            aria-label={`Tên key ${name} mới`}
            value={label}
            maxLength={40}
            placeholder="Tên (không bắt buộc)"
            style={{ maxWidth: 180 }}
            onChange={(event) => setLabel(event.target.value)}
          />
          <Input.Password
            aria-label={`Dán key ${name}`}
            value={key}
            autoComplete="new-password"
            placeholder="Dán API key vào đây…"
            onChange={(event) => setKey(event.target.value)}
            onPressEnter={() => key.trim() && void add()}
          />
          <Button disabled={!key.trim()} loading={busy} onClick={() => void add()}>
            Thêm key
          </Button>
        </Space.Compact>
      </Flex>
    </div>
  );
}
