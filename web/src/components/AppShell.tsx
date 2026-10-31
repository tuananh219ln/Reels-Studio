"use client";

import {
  BookOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  CustomerServiceOutlined,
  KeyOutlined,
  LogoutOutlined,
  MenuOutlined,
  EditOutlined,
  FacebookOutlined,
  NotificationOutlined,
  PlaySquareOutlined,
  ShoppingOutlined,
  TeamOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Drawer, Dropdown, Flex, Grid, Layout, Menu, Result, Spin } from "antd";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Me } from "@/lib/api";
import { ChangePasswordModal, RenameModal } from "./AccountModals";
import Logo from "./Logo";
import { MeContext } from "./MeContext";
import UserAvatar from "./UserAvatar";

const POST_GROUP = "group:posts";

const NAV = [
  { key: "/videos", icon: <PlaySquareOutlined />, label: "Video" },
  {
    key: POST_GROUP,
    icon: <NotificationOutlined />,
    label: "Đăng bài",
    children: [
      { key: "/posts", icon: <UnorderedListOutlined />, label: "Bài đăng" },
      { key: "/calendar", icon: <CalendarOutlined />, label: "Lịch đăng bài" },
    ],
  },
  { key: "/knowledge", icon: <BookOutlined />, label: "Kho kiến thức" },
  { key: "/music", icon: <CustomerServiceOutlined />, label: "Thư viện nhạc" },
  { key: "/affiliate", icon: <ShoppingOutlined />, label: "Affiliate Shopee" },
  { key: "/users", icon: <TeamOutlined />, label: "Quản lý người dùng" },
  { key: "/jobs", icon: <ClockCircleOutlined />, label: "Job logs" },
  { key: "/fanpages", icon: <FacebookOutlined />, label: "Kết nối Fanpage" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const screens = Grid.useBreakpoint();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modal, setModal] = useState<"password" | "name" | null>(null);

  const load = useCallback(() => {
    setError(null);
    api<Me>("/me")
      .then((loaded) => (loaded.must_change_password ? router.replace("/change-password") : setMe(loaded)))
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [router]);

  useEffect(load, [load]);

  async function logout() {
    await api("/auth/logout", "POST").catch(() => undefined);
    router.replace("/login");
  }

  if (error) {
    return (
      <Result
        status="warning"
        title={error}
        extra={
          <Button type="primary" onClick={load}>
            Thử lại
          </Button>
        }
      />
    );
  }
  if (!me) {
    return (
      <Flex justify="center" align="center" style={{ minHeight: "100vh" }}>
        <Spin size="large" />
      </Flex>
    );
  }

  const pageItem = (item: { key: string; icon: React.ReactNode; label: string }) => ({
    key: item.key,
    icon: item.icon,
    label: <Link href={item.key}>{item.label}</Link>,
  });
  const selected = NAV.flatMap((item) => item.children ?? [item]).find((item) => pathname.startsWith(item.key))?.key ?? "/videos";
  const menu = (
    <Menu
      mode="inline"
      selectedKeys={[selected]}
      defaultOpenKeys={[POST_GROUP]}
      style={{ border: "none", padding: "0 6px" }}
      items={NAV.map((item) =>
        item.children ? { ...item, children: item.children.map(pageItem) } : pageItem(item),
      )}
      onClick={() => setDrawerOpen(false)}
    />
  );
  const desktop = screens.lg ?? true;

  return (
    <MeContext.Provider value={{ me, setMe }}>
      <Layout style={{ minHeight: "100vh" }}>
        {desktop && (
          <Layout.Sider width={220} style={{ borderRight: "1px solid #EDEDED" }}>
            <div style={{ padding: "20px 20px 24px" }}>
              <Logo />
            </div>
            {menu}
          </Layout.Sider>
        )}
        <Drawer
          open={!desktop && drawerOpen}
          onClose={() => setDrawerOpen(false)}
          placement="left"
          size={260}
          title={<Logo />}
          styles={{ body: { padding: "8px 0" } }}
        >
          {menu}
        </Drawer>
        <Layout style={{ minWidth: 0 }}>
          <Layout.Header
            style={{
              height: 72,
              padding: "0 16px",
              borderBottom: "1px solid #EDEDED",
              display: "flex",
              alignItems: "center",
              justifyContent: desktop ? "flex-end" : "space-between",
            }}
          >
            {!desktop && (
              <Button aria-label="Mở menu" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />
            )}
            <Dropdown
              trigger={["click"]}
              menu={{
                items: [
                  { key: "password", icon: <KeyOutlined />, label: "Đổi mật khẩu", onClick: () => setModal("password") },
                  { key: "name", icon: <EditOutlined />, label: "Sửa tên", onClick: () => setModal("name") },
                  { type: "divider" },
                  { key: "logout", icon: <LogoutOutlined />, label: "Đăng xuất", onClick: logout },
                ],
              }}
            >
              <Button type="text" style={{ height: 44, display: "flex", alignItems: "center", gap: 10 }}>
                <UserAvatar initial={me.initial} />
                <span data-testid="header-name">{me.name}</span>
              </Button>
            </Dropdown>
          </Layout.Header>
          <Layout.Content style={{ padding: "32px 16px 40px", maxWidth: 1400, width: "100%", boxSizing: "border-box" }}>
            {children}
          </Layout.Content>
        </Layout>
      </Layout>
      <ChangePasswordModal open={modal === "password"} onClose={() => setModal(null)} />
      <RenameModal open={modal === "name"} onClose={() => setModal(null)} />
    </MeContext.Provider>
  );
}
