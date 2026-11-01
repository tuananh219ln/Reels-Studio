"use client";

import { App, Button, Card, Flex, Input, Popconfirm, Space, Switch, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";

type Key = { origin: "saved" | "unreadable" | "env" | null; hint: string; signup_url: string };
type Source = {
  id: string;
  label: string;
  kinds: string;
  key: Key | null;
  configured: boolean;
  enabled: boolean;
};
type AiImages = { configured: boolean; model: string; key: Key };
type Sources = {
  sources: Source[];
  ai_provider?: "gemini" | "cloudflare";
  ai_images: AiImages;
  ai_images_cloudflare?: AiImages & { account_id_set: boolean };
};

/** Paste, replace or remove one source's API key; the key itself is never shown again. */
function KeyField({
  name,
  label,
  value,
  onSaved,
  note,
}: {
  name: string;
  label: string;
  value: Key;
  onSaved: (data: Sources) => void;
  note?: string;
}) {
  const { message } = App.useApp();
  const [pasting, setPasting] = useState(value.origin === null || value.origin === "unreadable");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(apiKey: string) {
    setBusy(true);
    try {
      const data = await api<Sources>(`/settings/sources/${name}/key`, "PUT", { api_key: apiKey });
      onSaved(data);
      setKey("");
      const now =
        name === "gemini"
          ? data.ai_images.key
          : name === "cloudflare"
            ? data.ai_images_cloudflare?.key
            : data.sources.find((item) => item.id === name)?.key;
      setPasting(!now?.origin);
      message.success(apiKey ? `Đã lưu API key của ${label}` : `Đã xoá API key của ${label}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid={`key-${name}`}>
      <Typography.Text strong>API key</Typography.Text>
      {value.origin === "unreadable" && (
        <Typography.Text type="warning" style={{ display: "block" }}>
          Không đọc được key đã lưu (khoá mã hoá trong thư mục lưu trữ đã đổi). Hãy dán lại key.
        </Typography.Text>
      )}
      {!pasting ? (
        <Flex wrap gap={8} align="center" style={{ marginTop: 4 }}>
          <Typography.Text data-testid="key-status">
            {value.origin === "saved"
              ? `Đã lưu${value.hint ? `, kết thúc bằng …${value.hint}` : ""}`
              : "Đang dùng key trong file .env của máy chủ"}
          </Typography.Text>
          <Button size="small" onClick={() => setPasting(true)}>
            Dán key mới
          </Button>
          {value.origin === "saved" && (
            <Popconfirm
              title={`Xoá API key của ${label}?`}
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
        <Space.Compact style={{ width: "100%", maxWidth: 560, marginTop: 4 }}>
          <Input.Password
            aria-label={`API key ${label}`}
            value={key}
            autoComplete="new-password"
            placeholder="Dán API key vào đây"
            onChange={(event) => setKey(event.target.value)}
            onPressEnter={() => key.trim() && save(key)}
          />
          <Button type="primary" disabled={!key.trim()} loading={busy} onClick={() => save(key)}>
            Lưu key
          </Button>
          {value.origin !== null && value.origin !== "unreadable" && (
            <Button onClick={() => (setPasting(false), setKey(""))}>Huỷ</Button>
          )}
        </Space.Compact>
      )}
      <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, marginTop: 4 }}>
        {note ? `${note} ` : ""}Key được mã hoá khi lưu và không bao giờ hiện lại; key lưu ở đây được dùng thay key
        trong .env.{" "}
        <a href={value.signup_url} target="_blank" rel="noreferrer">
          Lấy key {label}
        </a>
      </Typography.Text>
    </div>
  );
}

const ready = (configured: boolean) =>
  configured ? <Tag color="success">Sẵn sàng</Tag> : <Tag color="warning">Chưa có key</Tag>;

/** The stock libraries the picker and "Tìm ảnh khác" use, their keys, and the AI image model's key. */
export default function SourcesPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<Sources | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api<Sources>("/settings/sources"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  async function toggle(source: Source, enabled: boolean) {
    setBusy(source.id);
    try {
      setData(await api<Sources>(`/settings/sources/${source.id}`, "PUT", { enabled }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Typography.Title level={2} style={{ margin: 0, fontWeight: 600 }}>
        Nguồn tư liệu
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ margin: "8px 0 16px", maxWidth: 760 }}>
        Các kho ảnh và video miễn phí mà hộp “Chọn từ kho ảnh/video” và nút “Tìm ảnh khác” dùng, cùng key tạo ảnh AI.
        Tắt một nguồn thì nó biến khỏi hộp chọn của cả nhóm.
      </Typography.Paragraph>
      <Flex vertical gap={16} style={{ maxWidth: 900 }}>
        {(data?.sources ?? []).map((source) => (
          <Card
            key={source.id}
            size="small"
            data-testid={`source-${source.id}`}
            title={
              <Flex wrap gap={8} align="center">
                <span>{source.label}</span>
                {ready(source.configured)}
              </Flex>
            }
            extra={
              <Flex gap={8} align="center">
                <Typography.Text type="secondary">Hiện trong hộp chọn</Typography.Text>
                <Switch
                  aria-label={`Bật ${source.label}`}
                  checked={source.enabled}
                  loading={busy === source.id}
                  onChange={(enabled) => toggle(source, enabled)}
                />
              </Flex>
            }
          >
            <Flex vertical gap={12}>
              <Typography.Text type="secondary">Cung cấp: {source.kinds}</Typography.Text>
              {source.key ? (
                <KeyField name={source.id} label={source.label} value={source.key} onSaved={setData} />
              ) : (
                source.key === null && <Typography.Text type="secondary">Không cần API key.</Typography.Text>
              )}
            </Flex>
          </Card>
        ))}
        {data && (
          <Card
            size="small"
            data-testid="source-gemini"
            title={
              <Flex wrap gap={8} align="center">
                <span>Ảnh AI cho cảnh thiếu (Gemini)</span>
                {ready(data.ai_images.configured)}
                {data.ai_provider === "gemini" && <Tag color="processing">Đang dùng</Tag>}
              </Flex>
            }
          >
            <Flex vertical gap={12}>
              <Typography.Text type="secondary">Model: {data.ai_images.model}</Typography.Text>
              {data.ai_images.key && (
                <KeyField name="gemini" label="Gemini" value={data.ai_images.key} onSaved={setData} />
              )}
            </Flex>
          </Card>
        )}
        {data?.ai_images_cloudflare && (
          <Card
            size="small"
            data-testid="source-cloudflare"
            title={
              <Flex wrap gap={8} align="center">
                <span>Ảnh AI cho cảnh thiếu (Cloudflare)</span>
                {ready(data.ai_images_cloudflare.configured)}
                {data.ai_provider === "cloudflare" && <Tag color="processing">Đang dùng</Tag>}
              </Flex>
            }
          >
            <Flex vertical gap={12}>
              <Typography.Text type="secondary">
                Model: {data.ai_images_cloudflare.model} · miễn phí khoảng 57 ảnh mỗi ngày (10.000 neurons).
              </Typography.Text>
              <KeyField
                name="cloudflare"
                label="Cloudflare"
                value={data.ai_images_cloudflare.key}
                onSaved={setData}
                note="Dán API token Workers AI của Cloudflare (quyền Workers AI › Read)."
              />
              {!data.ai_images_cloudflare.account_id_set && (
                <Typography.Text type="warning">
                  Máy chủ chưa có IMAGE_GEN_CF_ACCOUNT_ID (Account ID của Cloudflare) trong file .env.
                </Typography.Text>
              )}
            </Flex>
          </Card>
        )}
        {data?.ai_provider && (
          <Typography.Text type="secondary">
            Nguồn ảnh AI đang dùng được chọn bằng biến IMAGE_GEN_PROVIDER trong file .env của máy chủ (gemini hoặc
            cloudflare).
          </Typography.Text>
        )}
      </Flex>
    </>
  );
}
