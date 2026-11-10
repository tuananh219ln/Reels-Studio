"use client";

import EmptyState from "@/components/EmptyState";
import { DeleteOutlined, DisconnectOutlined, EditOutlined, LinkOutlined, PlusOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Avatar,
  Button,
  Card,
  Flex,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateAccount } from "@/lib/api";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import FormDrawer from "@/components/FormDrawer";

type Fields = { platform: "shopee" | "tiktok"; name: string; app_id?: string; secret?: string; profile_url?: string };

/** The signed-in member's own affiliate accounts. Nobody else sees them; a Secret only ever goes in. */
export default function AffiliateAccountsPage() {
  const { message } = App.useApp();
  const [accounts, setAccounts] = useState<AffiliateAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<AffiliateAccount | "new" | null>(null);
  const [checking, setChecking] = useState<number | null>(null);
  const [connecting, setConnecting] = useState(false);

  const reload = useCallback(async () => {
    try {
      setAccounts(await api<AffiliateAccount[]>("/affiliate-accounts"));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void reload();
  }, [reload]);

  // Back from TikTok's consent page: say how the connection went, once, then drop it from the address.
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const outcome = query.get("tiktok");
    if (outcome === "connected") {
      message.success("Đã kết nối tài khoản TikTok");
    } else if (outcome === "error") {
      message.error(query.get("message") || "Không kết nối được TikTok, hãy thử lại");
    }
    if (outcome) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [message]);

  /** "Kết nối TikTok": the api gives TikTok's consent page, and the browser goes there itself; TikTok then sends it
   * back here with ?tiktok=connected|error. Not a link to the api: the /api proxy in production follows redirects
   * itself instead of handing them to the browser. */
  async function connectTikTok() {
    setConnecting(true);
    try {
      const { url } = await api<{ url: string }>("/tiktok/oauth/start");
      window.location.assign(url);
    } catch (err) {
      message.error(errorMessage(err));
      setConnecting(false);
    }
  }

  async function disconnect(account: AffiliateAccount) {
    if (!account.tiktok_connection) {
      return;
    }
    try {
      await api(`/tiktok/connections/${account.tiktok_connection.id}`, "DELETE");
      message.success("Đã ngắt kết nối TikTok");
      await reload();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function save(account: AffiliateAccount, changes: Partial<Fields> & { active?: boolean }) {
    try {
      await api(`/affiliate-accounts/${account.id}`, "PUT", {
        platform: account.platform,
        name: account.name,
        app_id: account.app_id,
        profile_url: account.profile_url,
        active: account.active,
        ...changes,
      });
      await reload();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function check(account: AffiliateAccount) {
    setChecking(account.id);
    try {
      const result = await api<{ ok: boolean; error: string | null }>(
        `/affiliate-accounts/${account.id}/check`,
        "POST",
      );
      if (result.ok) {
        message.success("Shopee nhận App ID và Secret này");
      } else {
        message.error(result.error ?? "Shopee từ chối");
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setChecking(null);
    }
  }

  async function remove(account: AffiliateAccount) {
    try {
      await api(`/affiliate-accounts/${account.id}`, "DELETE");
      message.success("Đã xoá tài khoản");
      await reload();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Flex vertical gap={0}>
      <SettingsHeader
        title="Tài khoản affiliate"
        description="Tài khoản affiliate là của riêng bạn. Shopee: App ID và Secret lấy trong trang Shopee Affiliate › Open API (mỗi người tự đăng ký); có chúng, app tự tìm sản phẩm theo gợi ý của kịch bản và tạo link riêng cho từng Fanpage của bạn. TikTok: tài khoản bạn gắn giỏ TikTok Shop; bấm Kết nối TikTok để app gửi video lên TikTok của bạn (nháp hoặc đăng thẳng)."
        actions={
          <Space wrap>
            <Button icon={<LinkOutlined />} loading={connecting} onClick={connectTikTok}>
              Kết nối TikTok
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setTarget("new")}>
              Thêm tài khoản
            </Button>
          </Space>
        }
      />
      <Card styles={{ body: { padding: 0 } }}>
        <Table<AffiliateAccount>
          rowKey="id"
          loading={loading}
          dataSource={accounts}
          pagination={false}
          scroll={{ x: 760 }}
          locale={{ emptyText: <EmptyState description={"Chưa có tài khoản nào"} /> }}
          columns={[
            {
              title: "Tài khoản",
              key: "name",
              render: (_, account) => (
                <Flex vertical gap={2}>
                  <Space size={4}>
                    <Tag color={account.platform === "tiktok" ? "magenta" : "orange"}>{account.platform_label}</Tag>
                    <Typography.Text strong>{account.name}</Typography.Text>
                  </Space>
                  {account.platform === "shopee" ? (
                    <Typography.Text type="secondary">
                      App ID {account.app_id}, Secret …{account.secret_tail}
                    </Typography.Text>
                  ) : (
                    <a href={account.profile_url ?? undefined} target="_blank" rel="noreferrer">
                      {account.profile_url}
                    </a>
                  )}
                  {account.platform === "tiktok" && <TikTokConnectionState account={account} />}
                  {account.report_error && <Typography.Text type="warning">{account.report_error}</Typography.Text>}
                  {account.report_read_at && (
                    <Typography.Text type="secondary">
                      Đọc đơn lần cuối {formatDateTime(account.report_read_at)}
                    </Typography.Text>
                  )}
                </Flex>
              ),
            },
            {
              title: "Đang dùng",
              key: "active",
              width: 110,
              render: (_, account) => (
                <Switch
                  aria-label={`Dùng ${account.name}`}
                  checked={account.active}
                  onChange={(active) => save(account, { active })}
                />
              ),
            },
            {
              title: "Thao tác",
              key: "actions",
              width: 320,
              render: (_, account) => (
                <Space wrap>
                  {account.platform === "shopee" && (
                    <Button loading={checking === account.id} onClick={() => check(account)}>
                      Kiểm tra kết nối
                    </Button>
                  )}
                  {account.platform === "tiktok" &&
                    (account.tiktok_connection && !account.tiktok_connection.needs_reconnect ? (
                      <Popconfirm
                        title="Ngắt kết nối TikTok?"
                        description="App sẽ không gửi video lên tài khoản này nữa. Bài đã đăng không bị đụng tới."
                        okText="Ngắt kết nối"
                        cancelText="Huỷ"
                        onConfirm={() => disconnect(account)}
                      >
                        <Button icon={<DisconnectOutlined />}>Ngắt kết nối</Button>
                      </Popconfirm>
                    ) : (
                      <Button icon={<LinkOutlined />} loading={connecting} onClick={connectTikTok}>
                        {account.tiktok_connection ? "Kết nối lại" : "Kết nối TikTok"}
                      </Button>
                    ))}
                  <Button
                    aria-label={`Sửa ${account.name}`}
                    icon={<EditOutlined />}
                    onClick={() => setTarget(account)}
                  />
                  <Popconfirm
                    title="Xoá tài khoản này?"
                    description="Tài khoản đã có bài đăng hoặc đơn hàng thì chỉ ngừng dùng được."
                    okText="Xoá"
                    cancelText="Huỷ"
                    onConfirm={() => remove(account)}
                  >
                    <Button aria-label={`Xoá ${account.name}`} danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <AccountModal
        target={target}
        onClose={() => setTarget(null)}
        onDone={async () => {
          message.success("Đã lưu");
          setTarget(null);
          await reload();
        }}
      />
    </Flex>
  );
}

/** A TikTok account's connection through TikTok's API: who it is, how long it lasts, and whether to connect again. */
function TikTokConnectionState({ account }: { account: AffiliateAccount }) {
  const connection = account.tiktok_connection;
  if (!connection) {
    return (
      <Typography.Text type="secondary" data-testid="tiktok-connection">
        Chưa kết nối TikTok: chỉ ghi được bài đăng tay
      </Typography.Text>
    );
  }
  if (connection.needs_reconnect) {
    return (
      <Alert
        type="warning"
        showIcon
        data-testid="tiktok-connection"
        title={`Kết nối TikTok @${connection.username} đã hết hạn, hãy bấm Kết nối lại`}
        description={connection.last_error ?? undefined}
      />
    );
  }
  return (
    <Space size={6} data-testid="tiktok-connection">
      <Avatar size="small" src={connection.avatar_url ?? undefined}>
        {connection.display_name.slice(0, 1)}
      </Avatar>
      <Typography.Text>
        Đã kết nối @{connection.username}, còn hạn tới {formatDateTime(connection.refresh_expires_at)}
      </Typography.Text>
    </Space>
  );
}

function AccountModal({
  target,
  onClose,
  onDone,
}: {
  target: AffiliateAccount | "new" | null;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<Fields>();
  const [busy, setBusy] = useState(false);
  const platform = Form.useWatch("platform", form) ?? "shopee";
  const adding = target === "new";

  useEffect(() => {
    if (target === null) {
      return;
    }
    form.resetFields();
    form.setFieldsValue(
      target === "new"
        ? { platform: "shopee" }
        : {
            platform: target.platform,
            name: target.name,
            app_id: target.app_id ?? undefined,
            profile_url: target.profile_url ?? undefined,
          },
    );
  }, [form, target]);

  async function submit(fields: Fields) {
    if (target === null) {
      return;
    }
    setBusy(true);
    try {
      await (target === "new"
        ? api("/affiliate-accounts", "POST", fields)
        : api(`/affiliate-accounts/${target.id}`, "PUT", { ...fields, active: target.active }));
      await onDone();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={adding ? "Thêm tài khoản affiliate" : "Sửa tài khoản affiliate"}
      open={target !== null}
      onClose={onClose}
      onOk={() => form.submit()}
      okText={adding ? "Thêm" : "Lưu"}
      cancelText="Huỷ"
      confirmLoading={busy}
      forceRender
    >
      <Form form={form} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item label="Nền tảng" name="platform">
          <Select
            aria-label="Nền tảng"
            disabled={!adding}
            options={[
              { value: "shopee", label: "Shopee" },
              { value: "tiktok", label: "TikTok" },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="Tên tài khoản"
          name="name"
          rules={[{ required: true, whitespace: true, message: "Nhập tên để nhận ra tài khoản" }]}
        >
          <Input placeholder={platform === "shopee" ? "Shopee của An" : "TikTok Dưỡng Sinh"} />
        </Form.Item>
        {platform === "shopee" ? (
          <>
            <Form.Item
              label="App ID"
              name="app_id"
              rules={[{ required: true, whitespace: true, message: "Nhập App ID" }]}
            >
              <Input autoComplete="off" />
            </Form.Item>
            <Form.Item
              label="Secret"
              name="secret"
              rules={[{ required: adding, whitespace: true, message: "Nhập Secret" }]}
              extra={adding ? undefined : "Để trống để giữ Secret đã lưu."}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          </>
        ) : (
          <Form.Item
            label="Link kênh TikTok"
            name="profile_url"
            rules={[{ required: true, whitespace: true, message: "Dán link kênh TikTok" }]}
          >
            <Input placeholder="https://www.tiktok.com/@ten-kenh" />
          </Form.Item>
        )}
      </Form>
    </FormDrawer>
  );
}
