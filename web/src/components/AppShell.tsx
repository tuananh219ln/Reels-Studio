"use client";

import {
  BookOutlined,
  ClockCircleOutlined,
  FolderOpenOutlined,
  CustomerServiceOutlined,
  KeyOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  EditOutlined,
  FacebookOutlined,
  FileTextOutlined,
  PlaySquareOutlined,
  SettingOutlined,
  ShoppingOutlined,
  TeamOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Drawer, Dropdown, Flex, Grid, Layout, Menu, Result, Spin } from "antd";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Me } from "@/lib/api";
import { useStoredChoice } from "@/lib/storedChoice";
import { ChangePasswordModal, RenameModal } from "./AccountModals";
import Logo from "./Logo";
import { MeContext } from "./MeContext";
import UserAvatar from "./UserAvatar";
import { COLORS } from "@/app/theme";

// The menu in four headed groups, always open, in the order of the work: make it, post it and earn from it, the
// material it is made from, then running the app (decisions 2026-11-10).
const NAV: { key: string; label: string; children: { key: string; icon: React.ReactNode; label: string }[] }[] = [
  {
    key: "group:make",
    label: "Tạo nội dung",
    children: [
      { key: "/videos", icon: <PlaySquareOutlined />, label: "Video" },
      { key: "/articles", icon: <FileTextOutlined />, label: "Bài viết" },
    ],
  },
  {
    key: "group:post",
    label: "Đăng và kiếm tiền",
    children: [
      { key: "/posts", icon: <UnorderedListOutlined />, label: "Bài đăng" },
      { key: "/fanpages", icon: <FacebookOutlined />, label: "Quản lý Page" },
      { key: "/affiliate", icon: <ShoppingOutlined />, label: "Affiliate" },
    ],
  },
  {
    key: "group:library",
    label: "Tài nguyên",
    children: [
      { key: "/knowledge", icon: <BookOutlined />, label: "Kho kiến thức" },
      { key: "/media", icon: <FolderOpenOutlined />, label: "Kho tư liệu" },
      { key: "/music", icon: <CustomerServiceOutlined />, label: "Thư viện nhạc" },
    ],
  },
  {
    key: "group:admin",
    label: "Quản trị",
    children: [
      { key: "/users", icon: <TeamOutlined />, label: "Quản lý người dùng" },
      { key: "/jobs", icon: <ClockCircleOutlined />, label: "Nhật ký job" },
      // One page with tabs, the member's own then the team's (settings/layout.tsx), "Kết nối MCP" too.
      { key: "/settings", icon: <SettingOutlined />, label: "Cài đặt" },
    ],
  },
];

// The width of the menu folded to its icons, on a video's page.
const RAIL_WIDTH = 56;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const screens = Grid.useBreakpoint();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The computer's menu can be folded away to give a table the whole window; the choice stays on this browser.
  const [menuState, setMenuState] = useStoredChoice<"shown" | "hidden">("menu-hidden", "shown");
  const menuHidden = menuState === "hidden";
  const hideMenu = (hidden: boolean) => setMenuState(hidden ? "hidden" : "shown");
  // A video's editor wants the width: there the menu folds to a rail of icons, widened again with its button.
  const onVideo = /^\/videos\/\d+/.test(pathname);
  const [railOpen, setRailOpen] = useState(false);

  const [modal, setModal] = useState<"password" | "name" | null>(null);

  const load = useCallback(() => {
    api<Me>("/me")
      .then((loaded) => (loaded.must_change_password ? router.replace("/change-password") : setMe(loaded)))
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

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
          <Button
            type="primary"
            onClick={() => {
              setError(null);
              load();
            }}
          >
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
    // No prefetch: each would render that page on the web worker (about a second or more each) while the
    // current page is still loading; a click renders it then.
    label: (
      <Link href={item.key} prefetch={false}>
        {item.label}
      </Link>
    ),
  });
  const desktop = screens.lg ?? true;
  // A menu hidden elsewhere is a rail here: the editor's header starts where "Hiện menu" would float.
  const hidden = menuHidden && !onVideo;
  const rail = desktop && onVideo && !railOpen;
  const selected =
    NAV.flatMap((group) => group.children).find((item) => pathname.startsWith(item.key))?.key ?? "/videos";
  const menu = (
    <Menu
      mode="inline"
      selectedKeys={[selected]}
      style={{ border: "none", padding: "0 6px" }}
      items={NAV.map((group) => ({ type: "group" as const, ...group, children: group.children.map(pageItem) }))}
      onClick={({ key }) => {
        setDrawerOpen(false);
        // A rail shows only the icons: the click on one is the link.
        if (rail) router.push(key);
      }}
    />
  );
  const account = (
    <Dropdown
      trigger={["click"]}
      placement={desktop ? "topLeft" : "bottomRight"}
      menu={{
        items: [
          {
            key: "password",
            icon: <KeyOutlined />,
            label: "Đổi mật khẩu",
            onClick: () => setModal("password"),
          },
          { key: "name", icon: <EditOutlined />, label: "Sửa tên", onClick: () => setModal("name") },
          { type: "divider" },
          { key: "logout", icon: <LogoutOutlined />, label: "Đăng xuất", onClick: logout },
        ],
      }}
    >
      <Button
        type="text"
        data-testid="account"
        aria-label={screens.sm === false ? `Tài khoản ${me.name}` : undefined}
        style={{
          height: 48,
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: desktop ? "100%" : undefined,
          paddingInline: rail ? 0 : desktop ? 12 : 8,
          justifyContent: rail ? "center" : "flex-start",
        }}
      >
        <UserAvatar initial={me.initial} />
        {/* A phone keeps only the avatar, so the logo and the menu button fit beside it. */}
        {screens.sm !== false && !rail && (
          <span
            data-testid="header-name"
            style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {me.name}
          </span>
        )}
      </Button>
    </Dropdown>
  );

  return (
    <MeContext.Provider value={{ me, setMe }}>
      <Layout style={{ minHeight: "100vh" }}>
        {desktop && (
          // Sticky: on a long page (the video editor) the menu stays in reach while scrolling.
          <Layout.Sider
            width={240}
            collapsed={hidden || rail}
            collapsedWidth={hidden ? 0 : RAIL_WIDTH}
            trigger={null}
            style={{
              borderRight: `1px solid ${COLORS.border}`,
              position: "sticky",
              top: 0,
              height: "100vh",
            }}
          >
            {/* The menu on top, the member's account at the foot: on a computer there is no header bar. */}
            <Flex vertical style={{ height: "100%" }}>
              {rail ? (
                <Flex justify="center" style={{ padding: "20px 0 24px" }}>
                  <Button
                    type="text"
                    aria-label="Mở rộng menu"
                    icon={<MenuUnfoldOutlined />}
                    onClick={() => setRailOpen(true)}
                  />
                </Flex>
              ) : (
                <Flex justify="space-between" align="center" style={{ padding: "20px 12px 24px 20px" }}>
                  <Logo />
                  {/* On a video's page the menu folds back to its rail; elsewhere it hides away. */}
                  {onVideo ? (
                    <Button
                      type="text"
                      aria-label="Thu gọn menu"
                      icon={<MenuFoldOutlined />}
                      onClick={() => setRailOpen(false)}
                    />
                  ) : (
                    <Button
                      type="text"
                      aria-label="Ẩn menu"
                      icon={<MenuFoldOutlined />}
                      onClick={() => hideMenu(true)}
                    />
                  )}
                </Flex>
              )}
              <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>{menu}</div>
              <div style={{ padding: 8, borderTop: `1px solid ${COLORS.border}` }}>{account}</div>
            </Flex>
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
          {/* A phone has no room for the menu: a header with the menu button, the logo and the account. */}
          {!desktop && (
            <Layout.Header
              style={{
                height: 60,
                padding: "0 12px",
                position: "sticky",
                top: 0,
                zIndex: 10,
                borderBottom: `1px solid ${COLORS.border}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <Flex align="center" gap={12}>
                <Button aria-label="Mở menu" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />
                <Logo />
              </Flex>
              {account}
            </Layout.Header>
          )}
          <Layout.Content
            style={{
              // No max width: on a wide screen the tables and cards use the whole window.
              padding: desktop ? "32px 32px 48px" : "20px 16px 40px",
              width: "100%",
              boxSizing: "border-box",
            }}
          >
            {desktop && hidden && (
              <Button
                aria-label="Hiện menu"
                icon={<MenuUnfoldOutlined />}
                onClick={() => hideMenu(false)}
                style={{ position: "fixed", top: 12, left: 12, zIndex: 20 }}
              />
            )}
            {children}
          </Layout.Content>
        </Layout>
      </Layout>
      <ChangePasswordModal open={modal === "password"} onClose={() => setModal(null)} />
      <RenameModal open={modal === "name"} onClose={() => setModal(null)} />
    </MeContext.Provider>
  );
}
