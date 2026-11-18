"use client";

import {
  App,
  Button,
  Card,
  Col,
  Flex,
  Input,
  Popconfirm,
  Row,
  Segmented,
  Space,
  Switch,
  Tag,
  theme,
  Typography,
} from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api";
import { LastEdit, useLatestEdits } from "@/components/settings/SharedHistory";
import type { EditLogEntry } from "@/components/EditHistory";
import ApiKeyList from "@/components/settings/ApiKeyList";
import VieneuKeyCard from "@/components/settings/VieneuKeyCard";
import StatusText from "@/components/StatusText";

/** The history names a source's fields by the source ("Pexels · Khoá: đã đổi khoá …k3P1"). */
export const SOURCE_NAMES: Record<string, string> = {
  pixabay: "Pixabay",
  pexels: "Pexels",
  unsplash: "Unsplash",
  wikimedia: "Wikimedia",
  openverse: "Openverse",
  gemini: "Gemini",
  cloudflare: "Cloudflare",
  elevenlabs: "ElevenLabs",
};

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
export type Sources = {
  sources: Source[];
  ai_provider?: "gemini" | "cloudflare";
  /** The default was chosen on this page (not worked out from what is set up). */
  ai_provider_saved?: boolean;
  /** The style added to every AI photo prompt; `custom`: edited here rather than the default. */
  ai_style?: { value: string; default: string; custom: boolean };
  /** "Tự tìm ảnh sau khi viết kịch bản": a stock photo for every scene once the script is written. */
  auto_photos?: boolean;
  auto_footage?: boolean;
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
            placeholder="Dán API key vào đây…"
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
  configured ? <StatusText tone="success">Sẵn sàng</StatusText> : <StatusText tone="warning">Chưa có key</StatusText>;

/** The stock library "Tìm ảnh", the picker and "Tự tìm ảnh" start with (api routes_videos.STOCK_SOURCES[0]). */
const DEFAULT_STOCK = "pexels";

/** GET /settings/sources and its changes, shared by the stock, AI image and voice groups of the page. */
export function useSources() {
  const { message } = App.useApp();
  const [data, setData] = useState<Sources | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [style, setStyle] = useState<string | null>(null);
  // Read again after every save: each one answers with the page's data anew.
  const latest = useLatestEdits("settings_sources", data);

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

  async function run(kind: string, action: () => Promise<void>) {
    setBusy(kind);
    try {
      await action();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return {
    data,
    setData,
    load,
    busy,
    style,
    setStyle,
    latest,
    chooseProvider: (provider: "gemini" | "cloudflare") =>
      run("ai-provider", async () => {
        setData(await api<Sources>("/settings/image-provider", "PUT", { provider }));
        message.success(`Nguồn ảnh AI mặc định: ${provider === "cloudflare" ? "Cloudflare" : "Gemini"}`);
      }),
    setAutoPhotos: (enabled: boolean) =>
      run("auto-photos", async () => setData(await api<Sources>("/settings/auto-photos", "PUT", { enabled }))),
    setAutoFootage: (enabled: boolean) =>
      run("auto-footage", async () => setData(await api<Sources>("/settings/auto-footage", "PUT", { enabled }))),
    saveStyle: (value: string | null) =>
      run("ai-style", async () => {
        const saved = await api<Sources>("/settings/image-style", "PUT", { style: value });
        setData(saved);
        setStyle(saved.ai_style?.value ?? "");
        message.success(value === null ? "Đã dùng lại phong cách mặc định" : "Đã lưu phong cách ảnh AI");
      }),
    toggle: (source: Source, enabled: boolean) =>
      run(source.id, async () => setData(await api<Sources>(`/settings/sources/${source.id}`, "PUT", { enabled }))),
  };
}

export type SourcesState = ReturnType<typeof useSources>;

function Edited({ entry, id, title }: { entry: EditLogEntry | undefined; id: number; title: string }) {
  return <LastEdit entry={entry} entityType="settings_sources" entityId={id} title={title} owners={SOURCE_NAMES} />;
}

/** "Kho ảnh và video miễn phí": the libraries the picker, "Tìm ảnh" and the automatic search use, in this order. */
export function StockPanel({ state }: { state: SourcesState }) {
  const { token } = theme.useToken();
  const { data, busy } = state;
  const stock = data?.sources ?? [];
  const order = stock.filter((source) => source.enabled && source.configured).map((source) => source.label);
  return (
    <Flex vertical gap={16}>
      <Typography.Text type="secondary">
        Hộp “Chọn từ kho ảnh/video”, nút “Tìm ảnh” và việc tự tìm ảnh dùng các kho này, theo thứ tự dưới đây; mỗi nhóm
        chủ đề có thể tự sắp thứ tự ở Kho kiến thức. Tắt một kho thì nó biến khỏi hộp chọn của cả nhóm.
      </Typography.Text>
      {data?.auto_photos !== undefined && (
        <Card size="small" data-testid="auto-photos" style={{ background: token.colorFillQuaternary }}>
          <Flex gap={12} align="flex-start">
            <Switch
              aria-label="Tự tìm ảnh sau khi viết kịch bản"
              checked={data.auto_photos}
              loading={busy === "auto-photos"}
              disabled={busy !== null}
              onChange={(checked) => void state.setAutoPhotos(checked)}
              style={{ marginTop: 2 }}
            />
            <Flex vertical gap={4}>
              <Typography.Text strong>Tự tìm ảnh sau khi viết kịch bản</Typography.Text>
              <Typography.Text type="secondary">
                Viết kịch bản xong, app lấy cho mỗi cảnh một ảnh dọc từ các kho đang bật (không dùng ảnh AI, không trùng
                ảnh giữa các cảnh). Hãy xem lại ảnh của từng cảnh trước khi render và thay nếu sai món.
              </Typography.Text>
              {order.length > 0 && (
                <Typography.Text type="secondary" data-testid="stock-order">
                  Thứ tự tìm chung: {order.join(" → ")}
                </Typography.Text>
              )}
            </Flex>
          </Flex>
        </Card>
      )}
      {data?.auto_footage !== undefined && (
        <Card size="small" data-testid="auto-footage" style={{ background: token.colorFillQuaternary }}>
          <Flex gap={12} align="flex-start">
            <Switch
              aria-label="Tự tìm và chọn clip theo kịch bản"
              checked={data.auto_footage}
              loading={busy === "auto-footage"}
              disabled={busy !== null}
              onChange={(checked) => void state.setAutoFootage(checked)}
              style={{ marginTop: 2 }}
            />
            <Flex vertical gap={4}>
              <Typography.Text strong>Tự tìm và chọn clip theo kịch bản</Typography.Text>
              <Link prefetch={false} href="/videos/rework">
                Nâng cấp các video chưa đăng
              </Link>
              <Typography.Text type="secondary">
                Không cần tìm link: sau khi viết kịch bản, app tìm video công khai trên YouTube và các kho Pexels,
                Pixabay đang bật. AI xem khung hình, chọn và cắt đoạn đúng nội dung; không có clip phù hợp thì tìm ảnh.
                Giữ nguyên tư liệu đã chọn. Video xuyên suốt chỉ tìm clip cho nền chung.
              </Typography.Text>
              <Typography.Text type="secondary">
                Cần model đọc được ảnh ở mục AI viết kịch bản; tối đa 3 lượt gọi AI mỗi cảnh, có tính phí theo model và
                giọng đọc. App tạo giọng trước để cắt clip đủ dài, giọng được dùng lại khi render. Bật mục này cũng bật
                tự tìm ảnh. TikTok chưa được tự tìm kiếm.
              </Typography.Text>
            </Flex>
          </Flex>
        </Card>
      )}
      <Row gutter={[16, 16]}>
        {stock.map((source) => (
          <Col key={source.id} xs={24} lg={12} xxl={8}>
            <Card
              size="small"
              data-testid={`source-${source.id}`}
              style={{ height: "100%" }}
              title={
                <Flex wrap gap={6} align="center">
                  <span>{source.label}</span>
                  {ready(source.configured)}
                  {source.id === DEFAULT_STOCK && <Tag>Mặc định</Tag>}
                </Flex>
              }
              extra={
                <Switch
                  aria-label={`Bật ${source.label}`}
                  title="Hiện trong hộp chọn"
                  checked={source.enabled}
                  loading={busy === source.id}
                  onChange={(enabled) => state.toggle(source, enabled)}
                />
              }
            >
              <Flex vertical gap={12}>
                <Typography.Text type="secondary">Cung cấp: {source.kinds}</Typography.Text>
                {source.key ? (
                  <KeyField name={source.id} label={source.label} value={source.key} onSaved={state.setData} />
                ) : (
                  source.key === null && <Typography.Text type="secondary">Không cần API key.</Typography.Text>
                )}
              </Flex>
            </Card>
          </Col>
        ))}
      </Row>
      <Edited entry={state.latest["1"]} id={1} title="Kho ảnh và video miễn phí" />
    </Flex>
  );
}

/** "Ảnh AI": the default provider for "Tạo ảnh AI", the style added to every prompt, and both providers' keys. */
export function AiImagesPanel({ state }: { state: SourcesState }) {
  const { data, busy, style } = state;
  if (!data) return null;
  return (
    <Flex vertical gap={16}>
      {data.ai_provider && (
        <Card size="small" data-testid="ai-provider" title="Nguồn mặc định và phong cách">
          <Flex vertical gap={8}>
            <Segmented
              aria-label="Nguồn ảnh AI mặc định"
              value={data.ai_provider}
              disabled={busy !== null}
              onChange={(value) => void state.chooseProvider(value as "gemini" | "cloudflare")}
              options={[
                { label: "Cloudflare (miễn phí)", value: "cloudflare" },
                { label: "Gemini (tốn phí)", value: "gemini" },
              ]}
              style={{ alignSelf: "flex-start" }}
            />
            {/* What is in use, said once: the switch alone read as "chosen" even when the app picked it. */}
            <Typography.Text data-testid="ai-provider-in-use">
              Đang dùng: {data.ai_provider === "gemini" ? "Gemini, mỗi ảnh AI tốn phí" : "Cloudflare, miễn phí"}
              {data.ai_provider_saved
                ? "."
                : " (chưa ai chọn ở đây nên app tự lấy theo cấu hình máy chủ; bấm một nguồn để chọn hẳn)."}
            </Typography.Text>
            <Typography.Text type="secondary">
              Nút “Tạo ảnh AI” dùng nguồn mặc định; muốn dùng nguồn kia cho một lần bấm, chọn ở mũi tên cạnh nút. Hết
              lượt Cloudflare trong ngày thì app báo lỗi chứ không tự chuyển sang Gemini.
            </Typography.Text>
            {data.ai_style && style !== null && (
              <Flex vertical gap={8} style={{ marginTop: 8 }}>
                <Typography.Text strong>Phong cách ảnh AI</Typography.Text>
                <Input.TextArea
                  aria-label="Phong cách ảnh AI"
                  value={style}
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  maxLength={500}
                  onChange={(event) => state.setStyle(event.target.value)}
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
                    onClick={() => void state.saveStyle(style)}
                  >
                    Lưu phong cách
                  </Button>
                  {data.ai_style.custom && (
                    <Button disabled={busy !== null} onClick={() => void state.saveStyle(null)}>
                      Dùng mặc định
                    </Button>
                  )}
                </Space>
              </Flex>
            )}
          </Flex>
        </Card>
      )}
      <Row gutter={[16, 16]}>
        {data.ai_images_cloudflare && (
          <Col xs={24} lg={12}>
            <Card
              size="small"
              data-testid="source-cloudflare"
              style={{ height: "100%" }}
              title={
                <Flex wrap gap={6} align="center">
                  <span>Cloudflare</span>
                  {ready(data.ai_images_cloudflare.configured)}
                  {data.ai_provider === "cloudflare" && <Tag>Mặc định</Tag>}
                </Flex>
              }
            >
              <Flex vertical gap={12}>
                <Typography.Text type="secondary">
                  Model: {data.ai_images_cloudflare.model}, miễn phí khoảng 57 ảnh mỗi ngày (10.000 neurons).
                </Typography.Text>
                <KeyField
                  name="cloudflare"
                  label="Cloudflare"
                  value={data.ai_images_cloudflare.key}
                  onSaved={state.setData}
                  note="Dán API token Workers AI của Cloudflare (quyền Workers AI › Read)."
                />
                {!data.ai_images_cloudflare.account_id_set && (
                  <Typography.Text type="warning">
                    Máy chủ chưa có IMAGE_GEN_CF_ACCOUNT_ID (Account ID của Cloudflare) trong file .env.
                  </Typography.Text>
                )}
              </Flex>
            </Card>
          </Col>
        )}
        <Col xs={24} lg={12}>
          <Card
            size="small"
            data-testid="source-gemini"
            style={{ height: "100%" }}
            title={
              <Flex wrap gap={6} align="center">
                <span>Gemini</span>
                {ready(data.ai_images.configured)}
                {data.ai_provider === "gemini" && <Tag>Mặc định</Tag>}
              </Flex>
            }
          >
            <Flex vertical gap={12}>
              <Typography.Text type="secondary">
                Model: {data.ai_images.model}. Key này cũng là key chính của giọng đọc Gemini (mục Giọng đọc); ảnh AI
                luôn dùng key này.
              </Typography.Text>
              {data.ai_images.key && (
                <KeyField name="gemini" label="Gemini" value={data.ai_images.key} onSaved={state.setData} />
              )}
            </Flex>
          </Card>
        </Col>
      </Row>
      <Edited entry={state.latest["2"]} id={2} title="Ảnh AI và giọng đọc" />
    </Flex>
  );
}

/** "Giọng đọc": each narration service's main key and its backup keys, tried in order when one fails. */
export function VoicePanel({ state, vieneuFooter }: { state: SourcesState; vieneuFooter?: ReactNode }) {
  const { data } = state;
  if (!data) return null;
  const reload = () => void state.load();
  return (
    <Flex vertical gap={16}>
      <Typography.Text type="secondary">
        Mỗi cảnh đọc bằng key chính của dịch vụ; key sai hoặc hết hạn mức thì lời đọc tự chuyển sang key dự phòng kế
        tiếp (không đổi giọng), và dòng của key đó báo lỗi. Hết cả thì app báo lỗi.
      </Typography.Text>
      <Row gutter={[16, 16]}>
        {data.voices && (
          <Col xs={24} lg={12} xxl={8}>
            <Card
              size="small"
              data-testid="source-elevenlabs"
              style={{ height: "100%" }}
              title={
                <Flex wrap gap={6} align="center">
                  <span>ElevenLabs</span>
                  {ready(data.voices.configured)}
                </Flex>
              }
            >
              <Flex vertical gap={12}>
                <Typography.Text type="secondary">
                  Đọc lời từng cảnh khi render, và danh sách giọng ở Thiết lập mặc định.
                </Typography.Text>
                <KeyField name="elevenlabs" label="ElevenLabs" value={data.voices.key} onSaved={state.setData} />
                <ApiKeyList service="elevenlabs" onChanged={reload} />
              </Flex>
            </Card>
          </Col>
        )}
        <Col xs={24} lg={12} xxl={8}>
          <Card
            size="small"
            data-testid="voice-gemini"
            style={{ height: "100%" }}
            title={
              <Flex wrap gap={6} align="center">
                <span>Gemini</span>
                {ready(data.ai_images.configured)}
              </Flex>
            }
          >
            <Flex vertical gap={12}>
              <Typography.Text type="secondary">
                Các giọng Gemini hiện trong ô “Giọng” khi có key. Key chính là key Gemini ở mục Ảnh AI; gói miễn phí của
                Google giới hạn số lượt đọc mỗi ngày.
              </Typography.Text>
              <ApiKeyList service="gemini" onChanged={reload} />
            </Flex>
          </Card>
        </Col>
        <Col xs={24} lg={12} xxl={8}>
          <VieneuKeyCard onSaved={reload} footer={vieneuFooter} />
        </Col>
      </Row>
    </Flex>
  );
}
