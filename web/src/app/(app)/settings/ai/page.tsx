"use client";

import { ApiOutlined, CheckCircleFilled } from "@ant-design/icons";
import {
  Alert,
  App,
  AutoComplete,
  Button,
  Card,
  Col,
  Collapse,
  Flex,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type LlmProvider, type LlmSettings } from "@/lib/api";
import { COLORS } from "@/app/theme";

function StatusTag({ provider }: { provider: LlmProvider }) {
  if (provider.active) {
    return <Tag color="processing">Đang dùng</Tag>;
  }
  return provider.problem ? <Tag>Chưa cấu hình</Tag> : <Tag color="success">Sẵn sàng</Tag>;
}

/** One provider's key, base URL and model, its connection check, and "use it". */
function ProviderForm({ provider, onSaved }: { provider: LlmProvider; onSaved: (settings: LlmSettings) => void }) {
  const { message } = App.useApp();
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [model, setModel] = useState(provider.model);
  const [key, setKey] = useState("");
  const [pastingKey, setPastingKey] = useState(provider.key_source === null);
  const [models, setModels] = useState<string[] | null>(null);
  const [busy, setBusy] = useState<"save" | "key" | "check" | "use" | null>(null);
  const changed = baseUrl.trim() !== provider.base_url || model.trim() !== provider.model;

  async function run(kind: NonNullable<typeof busy>, action: () => Promise<void>) {
    setBusy(kind);
    try {
      await action();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const patch = (body: object) => api<LlmSettings>(`/settings/llm/${provider.id}`, "PATCH", body);

  const save = () =>
    run("save", async () => {
      const settings = await patch({ base_url: baseUrl, model });
      onSaved(settings);
      const saved = settings.providers.find((item) => item.id === provider.id)!;
      setBaseUrl(saved.base_url);
      setModel(saved.model);
      message.success(`Đã lưu ${provider.name}`);
    });

  const saveKey = () =>
    run("key", async () => {
      onSaved(await patch({ api_key: key }));
      setKey("");
      setPastingKey(false);
      message.success(`Đã lưu API key của ${provider.name}`);
    });

  const removeKey = () =>
    run("key", async () => {
      onSaved(await patch({ remove_key: true }));
      setPastingKey(true);
      message.success(`Đã xoá API key của ${provider.name}`);
    });

  const check = () =>
    run("check", async () => {
      const found = (await api<{ models: string[] }>(`/settings/llm/${provider.id}/models`, "POST")).models;
      setModels(found);
      if (found.length && !found.includes(provider.effective_model)) {
        message.warning(
          `Kết nối được (${found.length} model), nhưng không thấy model “${provider.effective_model || "(trống)"}” trong danh sách`,
        );
      } else {
        message.success(`Kết nối được ${provider.name} (${found.length} model)`);
      }
    });

  const use = () =>
    run("use", async () => {
      onSaved(await api<LlmSettings>("/settings/llm/active", "PUT", { provider: provider.id }));
      message.success(`Từ giờ kịch bản được viết bằng ${provider.name}`);
    });

  const modelOptions = [...new Set([...provider.model_suggestions, ...(models ?? [])])].map((value) => ({ value }));

  return (
    <Flex vertical gap={14} data-testid={`provider-${provider.id}`}>
      {provider.key_unreadable && (
        <Alert
          type="warning"
          showIcon
          title="Không đọc được API key đã lưu (khoá mã hoá trong thư mục lưu trữ đã đổi). Hãy dán lại key."
        />
      )}

      {provider.needs_key && (
        <div>
          <Typography.Text strong>API key</Typography.Text>
          {!pastingKey ? (
            <Flex wrap gap={8} align="center" style={{ marginTop: 4 }}>
              <Typography.Text data-testid="key-status">
                {provider.key_source === "saved"
                  ? `Đã lưu, kết thúc bằng …${provider.key_tail}`
                  : "Đang dùng key trong file .env của máy chủ"}
              </Typography.Text>
              <Button size="small" onClick={() => setPastingKey(true)}>
                Dán key mới
              </Button>
              {provider.key_source === "saved" && (
                <Popconfirm
                  title={`Xoá API key của ${provider.name}?`}
                  okText="Xoá"
                  cancelText="Huỷ"
                  okButtonProps={{ danger: true }}
                  onConfirm={removeKey}
                >
                  <Button size="small" danger loading={busy === "key"}>
                    Xoá key
                  </Button>
                </Popconfirm>
              )}
            </Flex>
          ) : (
            <Space.Compact style={{ width: "100%", marginTop: 4 }}>
              <Input.Password
                aria-label={`API key ${provider.name}`}
                value={key}
                autoComplete="new-password"
                placeholder="Dán API key vào đây"
                onChange={(event) => setKey(event.target.value)}
                onPressEnter={() => key.trim() && saveKey()}
              />
              <Button type="primary" disabled={!key.trim()} loading={busy === "key"} onClick={saveKey}>
                Lưu key
              </Button>
              {provider.key_source !== null && <Button onClick={() => (setPastingKey(false), setKey(""))}>Huỷ</Button>}
            </Space.Compact>
          )}
          <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, marginTop: 4 }}>
            Key được mã hoá khi lưu và không bao giờ hiện lại.
          </Typography.Text>
        </div>
      )}

      <div>
        <Typography.Text strong>Base URL</Typography.Text>
        <Input
          aria-label={`Base URL ${provider.name}`}
          style={{ marginTop: 4 }}
          value={baseUrl}
          placeholder={provider.default_base_url || "https://…/v1"}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
        <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, marginTop: 4 }}>
          {provider.default_base_url
            ? "Để trống để dùng địa chỉ mặc định ở trên."
            : "Địa chỉ API chuẩn OpenAI, thường kết thúc bằng /v1."}
        </Typography.Text>
      </div>

      <div>
        <Typography.Text strong>Model</Typography.Text>
        <AutoComplete
          aria-label={`Model ${provider.name}`}
          style={{ width: "100%", marginTop: 4 }}
          value={model}
          options={modelOptions}
          placeholder={provider.effective_model || "Gõ tên model, hoặc bấm “Kiểm tra kết nối” để xem danh sách"}
          onChange={setModel}
          filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
        />
        {models !== null && (
          <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, marginTop: 4 }}>
            Gợi ý lấy từ {provider.name}: {models.length} model.
          </Typography.Text>
        )}
      </div>

      {provider.problem && <Typography.Text type="warning">{provider.problem}</Typography.Text>}

      <Flex wrap gap={8}>
        <Button type="primary" disabled={!changed} loading={busy === "save"} onClick={save}>
          Lưu
        </Button>
        <Button icon={<ApiOutlined />} loading={busy === "check"} disabled={changed} onClick={check}>
          Kiểm tra kết nối
        </Button>
        {!provider.active && (
          <Button disabled={!!provider.problem || changed} loading={busy === "use"} onClick={use}>
            Dùng để viết kịch bản
          </Button>
        )}
      </Flex>
      {changed && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Lưu trước rồi mới kiểm tra kết nối.
        </Typography.Text>
      )}
      {provider.updated_at && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Cập nhật {formatDateTime(provider.updated_at)}
          {provider.updated_by ? ` · ${provider.updated_by}` : ""}
        </Typography.Text>
      )}
    </Flex>
  );
}

export default function AiSettingsPage() {
  const { message } = App.useApp();
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [open, setOpen] = useState<string[] | null>(null);
  const [switching, setSwitching] = useState(false);

  const load = useCallback(async () => {
    try {
      setSettings(await api<LlmSettings>("/settings/llm"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  async function choose(provider: string) {
    setSwitching(true);
    try {
      setSettings(await api<LlmSettings>("/settings/llm/active", "PUT", { provider }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSwitching(false);
    }
  }

  const active = settings?.providers.find((provider) => provider.active);

  return (
    <>
      {/* The choice beside the list on a wide screen, and staying in view while the list scrolls. */}
      <Row gutter={[24, 16]}>
        <Col xs={24} xl={9}>
          <div style={{ position: "sticky", top: 16 }}>
            <Typography.Paragraph type="secondary" style={{ margin: "0 0 16px" }}>
              Chọn nhà cung cấp AI viết kịch bản và nhân bản cho cả nhóm. Mỗi nhà cung cấp có API key, Base URL và model
              riêng. Đổi nhà cung cấp chỉ ảnh hưởng các kịch bản viết sau đó; mỗi video ghi lại model đã viết nó.
            </Typography.Paragraph>

            <Card size="small">
              <Flex wrap gap={12} align="center">
                <Typography.Text strong>Đang dùng để viết kịch bản:</Typography.Text>
                <Select
                  aria-label="Nhà cung cấp đang dùng"
                  style={{ minWidth: 0, flex: "1 1 240px" }}
                  loading={settings === null || switching}
                  value={settings?.active}
                  onChange={choose}
                  options={(settings?.providers ?? []).map((provider) => ({
                    value: provider.id,
                    disabled: !!provider.problem,
                    label: provider.problem
                      ? `${provider.name} (chưa cấu hình)`
                      : `${provider.name} · ${provider.effective_model}`,
                  }))}
                />
              </Flex>
              {active?.problem && (
                <Alert
                  type="error"
                  showIcon
                  style={{ marginTop: 12 }}
                  title={`Viết kịch bản sẽ lỗi: ${active.problem}`}
                />
              )}
            </Card>
          </div>
        </Col>
        <Col xs={24} xl={15}>
          {settings && (
            <Collapse
              style={{ background: "#fff" }}
              activeKey={open ?? [settings.active]}
              onChange={(keys) => setOpen(keys as string[])}
              items={settings.providers.map((provider) => ({
                key: provider.id,
                label: (
                  <Flex wrap gap={8} align="center">
                    {provider.active && <CheckCircleFilled style={{ color: COLORS.primary }} />}
                    <Typography.Text strong>{provider.name}</Typography.Text>
                    <StatusTag provider={provider} />
                    {!provider.problem && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {provider.effective_model}
                      </Typography.Text>
                    )}
                  </Flex>
                ),
                children: <ProviderForm provider={provider} onSaved={setSettings} />,
              }))}
            />
          )}
        </Col>
      </Row>
    </>
  );
}
