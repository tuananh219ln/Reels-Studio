"use client";

import { Alert, Button, Form, Input, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";
import CenteredCard from "@/components/CenteredCard";
import { ApiError, api, type Me } from "@/lib/api";
import { leaveSignIn, withNext } from "@/lib/next";

type Fields = { email: string; password: string };

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(fields: Fields) {
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("/auth/login", "POST", fields);
      if (me.must_change_password) {
        router.replace(withNext("/change-password"));
      } else {
        leaveSignIn((path) => router.replace(path));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <CenteredCard
      title="Đăng nhập"
      subtitle="Dùng email mà đội đã tạo cho bạn."
      footer={
        <Typography.Paragraph type="secondary" style={{ textAlign: "center", fontSize: 13 }}>
          Quên mật khẩu? Nhờ một thành viên trong đội đặt lại.
          <br />
          Công cụ nội bộ, không tự đăng ký tài khoản.
        </Typography.Paragraph>
      }
    >
      <Form<Fields> layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item label="Email" name="email" rules={[{ required: true, message: "Nhập email" }]}>
          <Input type="email" autoComplete="username" placeholder="ten@doi.vn" size="large" />
        </Form.Item>
        <Form.Item label="Mật khẩu" name="password" rules={[{ required: true, message: "Nhập mật khẩu" }]}>
          <Input.Password autoComplete="current-password" size="large" />
        </Form.Item>
        {error && <Alert type="error" title={error} showIcon style={{ marginBottom: 16 }} role="alert" />}
        <Button type="primary" htmlType="submit" size="large" block loading={busy}>
          Đăng nhập
        </Button>
      </Form>
    </CenteredCard>
  );
}
