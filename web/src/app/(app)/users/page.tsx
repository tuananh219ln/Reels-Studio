"use client";

import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import UserAvatar from "@/components/UserAvatar";
import { ApiError, api, formatDateTime, formatLastLogin, type UserRow } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import FormDrawer from "@/components/FormDrawer";

type NewUser = { email: string; name: string; password: string };

/** The "Thao tác gần nhất" column: what was last done to the member here. */
const ACTIONS: Record<NonNullable<UserRow["last_action"]>["action"], string> = {
  disable: "Vô hiệu hoá",
  enable: "Kích hoạt lại",
  temp_password: "Đặt mật khẩu tạm",
};

const passwordRules = [
  { required: true, message: "Nhập mật khẩu tạm" },
  { min: 8, message: "Mật khẩu phải có ít nhất 8 ký tự" },
];

export default function UsersPage() {
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [tempFor, setTempFor] = useState<UserRow | null>(null);
  const [disabling, setDisabling] = useState<UserRow | null>(null);

  const reload = useCallback(
    async (q: string) => {
      setLoading(true);
      try {
        setRows(await api<UserRow[]>(`/users?q=${encodeURIComponent(q)}`));
      } catch (err) {
        message.error(err instanceof ApiError ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [message],
  );

  useEffect(() => {
    const timer = setTimeout(() => reload(query), 250);
    return () => clearTimeout(timer);
  }, [query, reload]);

  /** Row actions: show the API's message on refusal, and always refresh the table afterwards. */
  async function act(path: string, success: string, body?: unknown) {
    try {
      await api(path, "POST", body);
      message.success(success);
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : String(err));
    }
    await reload(query);
  }

  function confirm(title: string, content: string, okText: string, run: () => Promise<void>, danger = false) {
    modal.confirm({ title, content, okText, cancelText: "Huỷ", okButtonProps: { danger }, onOk: run });
  }

  const columns: ColumnsType<UserRow> = [
    { title: "Ảnh", key: "avatar", width: 64, render: (_, row) => <UserAvatar initial={row.initial} /> },
    { title: "Email", dataIndex: "email" },
    { title: "Tên", dataIndex: "name", width: 170 },
    {
      title: "Trạng thái",
      key: "status",
      render: (_, row) => (row.is_active ? <Tag color="success">Hoạt động</Tag> : <Tag>Vô hiệu hoá</Tag>),
    },
    { title: "Đăng nhập gần nhất", key: "last_login", render: (_, row) => formatLastLogin(row.last_login_at) },
    { title: "Phiên hoạt động", dataIndex: "active_sessions", align: "right" },
    {
      title: "Thao tác gần nhất",
      key: "last_action",
      width: 190,
      render: (_, row) =>
        row.last_action ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="user-last-action">
            {ACTIONS[row.last_action.action]} bởi {row.last_action.by ?? "thành viên đã xoá"},{" "}
            {formatDateTime(row.last_action.at)}
          </Typography.Text>
        ) : null,
    },
    {
      title: "Thao tác",
      key: "actions",
      width: 500,
      // Small buttons: the three actions fit on one line of the row.
      render: (_, row) => {
        if (row.is_me) {
          return <Typography.Text type="secondary">Tài khoản của bạn</Typography.Text>;
        }
        if (!row.is_active) {
          return (
            <Space wrap size={6}>
              <Button
                size="small"
                onClick={() =>
                  confirm("Kích hoạt lại người dùng?", `${row.email} sẽ đăng nhập được trở lại.`, "Kích hoạt lại", () =>
                    act(`/users/${row.id}/enable`, "Đã kích hoạt lại"),
                  )
                }
              >
                Kích hoạt lại
              </Button>
              <Button size="small" onClick={() => setTempFor(row)}>
                Đặt mật khẩu tạm
              </Button>
            </Space>
          );
        }
        return (
          <Space wrap size={6}>
            <Button size="small" danger onClick={() => setDisabling(row)}>
              Vô hiệu hoá
            </Button>
            {/* Only a disabled account gets a temporary password: disable, set it, enable again. */}
            <Tooltip title="Chỉ đặt mật khẩu tạm cho tài khoản đã vô hiệu hoá: vô hiệu hoá, đặt mật khẩu tạm rồi kích hoạt lại.">
              <Button size="small" disabled>
                Đặt mật khẩu tạm
              </Button>
            </Tooltip>
            <Button
              size="small"
              onClick={() =>
                confirm(
                  "Đăng xuất khỏi mọi thiết bị?",
                  `${row.email} sẽ phải đăng nhập lại trên mọi thiết bị.`,
                  "Đăng xuất",
                  () => act(`/users/${row.id}/sign-out-all`, "Đã đăng xuất khỏi mọi thiết bị"),
                )
              }
            >
              Đăng xuất khỏi mọi thiết bị
            </Button>
          </Space>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        title="Quản lý người dùng"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            Thêm người dùng
          </Button>
        }
      >
        <Input
          aria-label="Tìm theo email hoặc tên"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo email hoặc tên"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 320, maxWidth: "100%" }}
        />
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<UserRow>
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={loading}
          pagination={false}
          // Fits a desktop content area; narrower screens scroll the table sideways.
          scroll={{ x: 1150 }}
          locale={{ emptyText: "Chưa có dữ liệu" }}
        />
      </Card>
      <AddUserModal
        open={adding}
        onClose={() => setAdding(false)}
        onAdded={() => {
          setAdding(false);
          reload(query);
        }}
      />
      <DisableModal
        row={disabling}
        members={rows.filter((member) => member.is_active && member.id !== disabling?.id)}
        onClose={() => setDisabling(null)}
        onDisable={async (transferTo) => {
          if (disabling) {
            await act(`/users/${disabling.id}/disable`, "Đã vô hiệu hoá", { transfer_to: transferTo });
          }
          setDisabling(null);
        }}
      />
      <TempPasswordModal
        row={tempFor}
        onClose={() => setTempFor(null)}
        onSave={async (password) => {
          if (tempFor) {
            await act(`/users/${tempFor.id}/temp-password`, "Đã đặt mật khẩu tạm", { password });
          }
          setTempFor(null);
        }}
      />
    </>
  );
}

function AddUserModal({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: () => void }) {
  const { message } = App.useApp();
  const [form] = Form.useForm<NewUser>();
  const [busy, setBusy] = useState(false);

  async function submit(fields: NewUser) {
    setBusy(true);
    try {
      await api("/users", "POST", fields);
      message.success(`Đã thêm ${fields.email.trim().toLowerCase()}`);
      form.resetFields();
      onAdded();
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Thêm người dùng"
      open={open}
      onClose={onClose}
      onOk={() => form.submit()}
      okText="Thêm"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item label="Email" name="email" rules={[{ required: true, message: "Nhập email" }]}>
          <Input type="email" placeholder="ten@doi.vn" />
        </Form.Item>
        <Form.Item
          label="Tên"
          name="name"
          rules={[
            { required: true, whitespace: true, message: "Tên phải từ 1 đến 60 ký tự" },
            { max: 60, message: "Tên phải từ 1 đến 60 ký tự" },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          label="Mật khẩu tạm"
          name="password"
          rules={passwordRules}
          extra="Gửi mật khẩu này cho người mới; họ phải đổi ở lần đăng nhập đầu."
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </FormDrawer>
  );
}

function TempPasswordModal({
  row,
  onClose,
  onSave,
}: {
  row: UserRow | null;
  onClose: () => void;
  onSave: (password: string) => Promise<void>;
}) {
  const [form] = Form.useForm<{ password: string }>();
  const [busy, setBusy] = useState(false);

  return (
    <FormDrawer
      title="Đặt mật khẩu tạm"
      open={row !== null}
      onClose={onClose}
      onOk={() => form.submit()}
      okText="Lưu"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        {row?.email} sẽ bị đăng xuất khỏi mọi thiết bị và phải đổi mật khẩu khi đăng nhập lại.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={async ({ password }) => {
          setBusy(true);
          await onSave(password);
          setBusy(false);
        }}
      >
        <Form.Item label="Mật khẩu tạm" name="password" rules={passwordRules}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </FormDrawer>
  );
}

/** "Vô hiệu hoá": the member's name typed to confirm, and, if wanted, the active member who takes their Pages, topic
 * groups, plan ideas and templates ("Chuyển quyền sở hữu cho…"). */
function DisableModal({
  row,
  members,
  onClose,
  onDisable,
}: {
  row: UserRow | null;
  members: UserRow[];
  onClose: () => void;
  onDisable: (transferTo: number | null) => Promise<void>;
}) {
  const [typed, setTyped] = useState("");
  const [transferTo, setTransferTo] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const matches = row !== null && typed.trim() === row.name.trim();

  return (
    <Modal
      title="Vô hiệu hoá người dùng?"
      open={row !== null}
      onCancel={onClose}
      okText="Vô hiệu hoá"
      cancelText="Huỷ"
      okButtonProps={{ danger: true, disabled: !matches }}
      confirmLoading={busy}
      destroyOnHidden
      afterClose={() => {
        setTyped("");
        setTransferTo(null);
      }}
      onOk={async () => {
        setBusy(true);
        await onDisable(transferTo);
        setBusy(false);
      }}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Typography.Text>{row?.email} sẽ không đăng nhập được và bị đăng xuất khỏi mọi thiết bị ngay.</Typography.Text>
        <div>
          <Typography.Text>Chuyển quyền sở hữu cho (không bắt buộc)</Typography.Text>
          <Select
            aria-label="Chuyển quyền sở hữu cho"
            allowClear
            placeholder="Giữ nguyên, không chuyển"
            value={transferTo ?? undefined}
            onChange={(value) => setTransferTo(value ?? null)}
            options={members.map((member) => ({ value: member.id, label: member.name }))}
            style={{ width: "100%", marginTop: 4 }}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Page, nhóm chủ đề, ý tưởng kế hoạch và mẫu dựng của người này chuyển sang người được chọn. Page bỏ tài khoản
            Shopee, TikTok và bán tự động cũ để người nhận tự gắn lại.
          </Typography.Text>
        </div>
        <div>
          <Typography.Text>
            Nhập tên <Typography.Text strong>{row?.name}</Typography.Text> để xác nhận
          </Typography.Text>
          <Input
            aria-label="Nhập tên để xác nhận"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            style={{ marginTop: 4 }}
          />
        </div>
      </Space>
    </Modal>
  );
}
