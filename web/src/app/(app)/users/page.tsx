"use client";

import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Form, Input, Modal, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import UserAvatar from "@/components/UserAvatar";
import { ApiError, api, formatLastLogin, type UserRow } from "@/lib/api";

type NewUser = { email: string; name: string; password: string };

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
      title: "Thao tác",
      key: "actions",
      width: 500,
      render: (_, row) => {
        if (row.is_me) {
          return <Typography.Text type="secondary">Tài khoản của bạn</Typography.Text>;
        }
        if (!row.is_active) {
          return (
            <Button
              onClick={() =>
                confirm("Kích hoạt lại người dùng?", `${row.email} sẽ đăng nhập được trở lại.`, "Kích hoạt lại", () =>
                  act(`/users/${row.id}/enable`, "Đã kích hoạt lại"),
                )
              }
            >
              Kích hoạt lại
            </Button>
          );
        }
        return (
          <Space wrap>
            <Button
              danger
              onClick={() =>
                confirm(
                  "Vô hiệu hoá người dùng?",
                  `${row.email} sẽ không đăng nhập được và bị đăng xuất khỏi mọi thiết bị ngay.`,
                  "Vô hiệu hoá",
                  () => act(`/users/${row.id}/disable`, "Đã vô hiệu hoá"),
                  true,
                )
              }
            >
              Vô hiệu hoá
            </Button>
            <Button onClick={() => setTempFor(row)}>Đặt mật khẩu tạm</Button>
            <Button
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
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Quản lý người dùng
      </Typography.Title>
      <Flex wrap gap={12} justify="space-between" style={{ marginBottom: 16 }}>
        <Input
          aria-label="Tìm theo email hoặc tên"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo email hoặc tên"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ maxWidth: 320 }}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
          Thêm người dùng
        </Button>
      </Flex>
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
    <Modal
      title="Thêm người dùng"
      open={open}
      onCancel={onClose}
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
    </Modal>
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
    <Modal
      title="Đặt mật khẩu tạm"
      open={row !== null}
      onCancel={onClose}
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
    </Modal>
  );
}
