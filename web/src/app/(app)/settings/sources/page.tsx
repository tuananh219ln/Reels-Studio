"use client";

import { App, Button, Card, Flex, Input, Popconfirm, Segmented, Space, Switch, Tag, Typography } from "antd";
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
  /** The default was chosen on this page (not worked out from what is set up). */
  ai_provider_saved?: boolean;
  /** The style added to every AI photo prompt; `custom`: edited here rather than the default. */
  ai_style?: { value: string; default: string; custom: boolean };
  /** "Tự tìm ảnh sau khi viết kịch bản": a stock photo for every scene once the script is written. */
  auto_photos?: boolean;
  ai_images: AiImages;
  ai_images_cloudflare?: AiImages & { account_id_set: boolean };
  voices?: { configured: boolean; key: Key };
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
            : name === "elevenlabs"
              ? data.voices?.key
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

/** The stock libraries the picker and "Tìm ảnh khác" use, their keys, the AI image models' keys and ElevenLabs'. */
export default function SourcesPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<Sources | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [style, setStyle] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const loaded = await api<Sources>("/settings/sources");
      setData(loaded);
      setStyle(loaded.ai_style?.value ?? null);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  async function chooseProvider(provider: "gemini" | "cloudflare") {
    setBusy("ai-provider");
    try {
      setData(await api<Sources>("/settings/image-provider", "PUT", { provider }));
      message.success(`Nguồn ảnh AI mặc định: ${provider === "cloudflare" ? "Cloudflare" : "Gemini"}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function setAutoPhotos(enabled: boolean) {
    setBusy("auto-photos");
    try {
      setData(await api<Sources>("/settings/auto-photos", "PUT", { enabled }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function saveStyle(style: string | null) {
    setBusy("ai-style");
    try {
      const saved = await api<Sources>("/settings/image-style", "PUT", { style });
      setData(saved);
      setStyle(saved.ai_style?.value ?? "");
      message.success(style === null ? "Đã dùng lại phong cách mặc định" : "Đã lưu phong cách ảnh AI");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

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
      <Typography.Paragraph type="secondary" style={{ margin: "0 0 16px", maxWidth: 760 }}>
        Các kho ảnh và video miễn phí mà hộp “Chọn từ kho ảnh/video” và nút “Tìm ảnh khác” dùng, cùng key tạo ảnh AI và
        key giọng đọc. Tắt một nguồn thì nó biến khỏi hộp chọn của cả nhóm.
      </Typography.Paragraph>
      <Flex vertical gap={16} style={{ maxWidth: 900 }}>
        {data?.auto_photos !== undefined && (
          <Card size="small" data-testid="auto-photos">
            <Flex vertical gap={4}>
              <Flex gap={8} align="center">
                <Switch
                  aria-label="Tự tìm ảnh sau khi viết kịch bản"
                  checked={data.auto_photos}
                  loading={busy === "auto-photos"}
                  disabled={busy !== null}
                  onChange={(checked) => void setAutoPhotos(checked)}
                />
                <Typography.Text strong>Tự tìm ảnh sau khi viết kịch bản</Typography.Text>
              </Flex>
              <Typography.Text type="secondary">
                Viết kịch bản xong, app lấy cho mỗi cảnh một ảnh dọc từ các kho miễn phí đang bật bên dưới (không dùng
                ảnh AI, không trùng ảnh giữa các cảnh). Ảnh tự chọn có nhãn “Tự chọn, kiểm tra lại” để bạn xem và thay
                nếu sai món.
              </Typography.Text>
            </Flex>
          </Card>
        )}
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
        {data?.ai_provider && (
          <Card size="small" data-testid="ai-provider" title="Ảnh AI">
            <Flex vertical gap={8}>
              <Segmented
                aria-label="Nguồn ảnh AI mặc định"
                value={data.ai_provider}
                disabled={busy !== null}
                onChange={(value) => void chooseProvider(value as "gemini" | "cloudflare")}
                options={[
                  { label: "Cloudflare (miễn phí)", value: "cloudflare" },
                  { label: "Gemini (tốn phí)", value: "gemini" },
                ]}
                style={{ alignSelf: "flex-start" }}
              />
              <Typography.Text type="secondary">
                Các nút “Tạo ảnh AI” dùng nguồn này. Muốn dùng nguồn kia cho một lần bấm, chọn ở mũi tên cạnh nút. Hết
                lượt Cloudflare trong ngày thì app báo lỗi chứ không tự chuyển sang Gemini (tốn phí).
                {!data.ai_provider_saved && " Chưa chọn: app dùng Cloudflare nếu đã có token, không thì dùng Gemini."}
              </Typography.Text>
              {data.ai_style && style !== null && (
                <Flex vertical gap={8} style={{ marginTop: 8 }}>
                  <Typography.Text strong>Phong cách ảnh AI</Typography.Text>
                  <Input.TextArea
                    aria-label="Phong cách ảnh AI"
                    value={style}
                    autoSize={{ minRows: 2, maxRows: 5 }}
                    maxLength={500}
                    onChange={(event) => setStyle(event.target.value)}
                  />
                  <Typography.Text type="secondary">
                    Thêm vào sau prompt của mọi cảnh khi tạo ảnh AI, để các cảnh cùng một kiểu (nên viết tiếng Anh). Để
                    trống thì chỉ dùng prompt của cảnh.
                  </Typography.Text>
                  <Space>
                    <Button
                      type="primary"
                      loading={busy === "ai-style"}
                      disabled={busy !== null || style.trim() === data.ai_style.value}
                      onClick={() => void saveStyle(style)}
                    >
                      Lưu phong cách
                    </Button>
                    {data.ai_style.custom && (
                      <Button disabled={busy !== null} onClick={() => void saveStyle(null)}>
                        Dùng mặc định
                      </Button>
                    )}
                  </Space>
                </Flex>
              )}
            </Flex>
          </Card>
        )}
        {data && (
          <Card
            size="small"
            data-testid="source-gemini"
            title={
              <Flex wrap gap={8} align="center">
                <span>Ảnh AI (Gemini)</span>
                {ready(data.ai_images.configured)}
                {data.ai_provider === "gemini" && <Tag color="processing">Mặc định</Tag>}
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
                <span>Ảnh AI (Cloudflare)</span>
                {ready(data.ai_images_cloudflare.configured)}
                {data.ai_provider === "cloudflare" && <Tag color="processing">Mặc định</Tag>}
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
        {data?.voices && (
          <Card
            size="small"
            data-testid="source-elevenlabs"
            title={
              <Flex wrap gap={8} align="center">
                <span>Giọng đọc (ElevenLabs)</span>
                {ready(data.voices.configured)}
              </Flex>
            }
          >
            <Flex vertical gap={12}>
              <Typography.Text type="secondary">
                Đọc lời từng cảnh khi render và danh sách giọng ở Thiết lập mặc định.
              </Typography.Text>
              <KeyField name="elevenlabs" label="ElevenLabs" value={data.voices.key} onSaved={setData} />
            </Flex>
          </Card>
        )}
      </Flex>
    </>
  );
}
