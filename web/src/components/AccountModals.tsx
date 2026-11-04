"use client";

import { App, Form, Input } from "antd";
import { useState } from "react";
import { ApiError, api, type Me } from "@/lib/api";
import { useMe } from "./MeContext";
import NewPasswordFields from "./NewPasswordFields";
import FormDrawer from "@/components/FormDrawer";

type PasswordFields = { current_password: string; new_password: string; confirm_password: string };

export function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const [form] = Form.useForm<PasswordFields>();
  const [busy, setBusy] = useState(false);

  async function submit(fields: PasswordFields) {
    setBusy(true);
    try {
      await api<Me>("/me/password", "POST", {
        current_password: fields.current_password,
        new_password: fields.new_password,
      });
      message.success("Đã đổi mật khẩu. Các thiết bị khác đã được đăng xuất.");
      form.resetFields();
      onClose();
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Đổi mật khẩu"
      open={open}
      onClose={onClose}
      onOk={() => form.submit()}
      okText="Lưu"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item
          label="Mật khẩu hiện tại"
          name="current_password"
          rules={[{ required: true, message: "Nhập mật khẩu hiện tại" }]}
        >
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <NewPasswordFields />
      </Form>
    </FormDrawer>
  );
}

export function RenameModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const { me, setMe } = useMe();
  const [form] = Form.useForm<{ name: string }>();
  const [busy, setBusy] = useState(false);

  async function submit({ name }: { name: string }) {
    setBusy(true);
    try {
      setMe(await api<Me>("/me", "PATCH", { name }));
      message.success("Đã đổi tên");
      onClose();
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Sửa tên"
      open={open}
      onClose={onClose}
      onOk={() => form.submit()}
      okText="Lưu"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" requiredMark={false} onFinish={submit} initialValues={{ name: me.name }}>
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
      </Form>
    </FormDrawer>
  );
}
