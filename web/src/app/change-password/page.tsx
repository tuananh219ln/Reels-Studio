"use client";

import { Alert, Button, Flex, Form, Spin } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import CenteredCard from "@/components/CenteredCard";
import NewPasswordFields from "@/components/NewPasswordFields";
import { ApiError, api, type Me } from "@/lib/api";
import { leaveSignIn } from "@/lib/next";

type Fields = { new_password: string; confirm_password: string };

/** Forced change after logging in with a temporary password: no current password asked. */
export default function ChangePasswordPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Me>("/me")
      .then((me) => (me.must_change_password ? setReady(true) : leaveSignIn((path) => router.replace(path))))
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [router]);

  async function submit(fields: Fields) {
    setBusy(true);
    setError(null);
    try {
      await api<Me>("/me/password", "POST", { new_password: fields.new_password });
      leaveSignIn((path) => router.replace(path));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  }

  async function logout() {
    await api("/auth/logout", "POST").catch(() => undefined);
    router.replace("/login");
  }

  return (
    <CenteredCard title="Đổi mật khẩu" subtitle="Bạn đang dùng mật khẩu tạm. Đặt mật khẩu mới để tiếp tục.">
      {!ready && !error && (
        <Flex justify="center">
          <Spin />
        </Flex>
      )}
      {error && <Alert type="error" title={error} showIcon style={{ marginBottom: 16 }} role="alert" />}
      {ready && (
        <Form<Fields> layout="vertical" requiredMark={false} onFinish={submit}>
          <NewPasswordFields />
          <Button type="primary" htmlType="submit" block loading={busy}>
            Lưu mật khẩu mới
          </Button>
          <Button type="link" block onClick={logout} style={{ marginTop: 8 }}>
            Đăng xuất
          </Button>
        </Form>
      )}
    </CenteredCard>
  );
}
