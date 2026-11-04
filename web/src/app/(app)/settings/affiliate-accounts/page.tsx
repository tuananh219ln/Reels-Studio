"use client";

import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Form, Input, Popconfirm, Select, Space, Switch, Table, Tag, Typography } from "antd";
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
        description="Tài khoản affiliate là của riêng bạn. Shopee: App ID và Secret lấy trong trang Shopee Affiliate › Open API (mỗi người tự đăng ký); có chúng, app tự tìm sản phẩm theo gợi ý của kịch bản và tạo link riêng cho từng Fanpage của bạn. TikTok: tài khoản bạn đăng tay và gắn giỏ TikTok Shop."
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setTarget("new")}>
            Thêm tài khoản
          </Button>
        }
      />
      <Card styles={{ body: { padding: 0 } }}>
        <Table<AffiliateAccount>
          rowKey="id"
          loading={loading}
          dataSource={accounts}
          pagination={false}
          scroll={{ x: 760 }}
          locale={{ emptyText: "Chưa có tài khoản nào" }}
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
                      App ID {account.app_id} · Secret …{account.secret_tail}
                    </Typography.Text>
                  ) : (
                    <a href={account.profile_url ?? undefined} target="_blank" rel="noreferrer">
                      {account.profile_url}
                    </a>
                  )}
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
              width: 260,
              render: (_, account) => (
                <Space wrap>
                  {account.platform === "shopee" && (
                    <Button loading={checking === account.id} onClick={() => check(account)}>
                      Kiểm tra kết nối
                    </Button>
                  )}
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
