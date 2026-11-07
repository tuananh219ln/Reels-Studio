"use client";

import {
  ControlOutlined,
  DesktopOutlined,
  PictureOutlined,
  RobotOutlined,
  ShoppingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Flex, Grid, Tabs, Typography } from "antd";
import { usePathname, useRouter } from "next/navigation";
import PageHeader from "@/components/PageHeader";

/** The "Cấu hình" tabs; each tab is its own page, so a link or a reload opens the same tab. */
const CONFIG_TABS = [
  {
    key: "/settings/defaults",
    label: "Thiết lập mặc định",
    hint: "Video mới bắt đầu thế nào",
    icon: <ControlOutlined />,
  },
  { key: "/settings/templates", label: "Mẫu dựng", hint: "Hiệu ứng áp sẵn cho video", icon: <ThunderboltOutlined /> },
  { key: "/settings/ai", label: "Mô hình AI", hint: "AI viết kịch bản", icon: <RobotOutlined /> },
  { key: "/settings/sources", label: "Nguồn tư liệu", hint: "Kho ảnh, ảnh AI, giọng đọc", icon: <PictureOutlined /> },
  {
    key: "/settings/affiliate-accounts",
    label: "Tài khoản affiliate",
    hint: "Shopee và TikTok của bạn",
    icon: <ShoppingOutlined />,
  },
  { key: "/settings/render-nodes", label: "Máy render", hint: "Render trên máy của bạn", icon: <DesktopOutlined /> },
];

/** On a wide screen the tabs are a list down the left, each with a line on what it holds, beside the tab's page; on
 * a narrower one they are a row above it. */
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const wide = Grid.useBreakpoint().xl ?? false;
  const active = CONFIG_TABS.find((tab) => pathname.startsWith(tab.key))?.key ?? CONFIG_TABS[0].key;
  const items = CONFIG_TABS.map((tab) => ({
    key: tab.key,
    label: wide ? (
      <Flex gap={10} align="flex-start" style={{ textAlign: "left", padding: "2px 0" }}>
        <span style={{ fontSize: 16, lineHeight: "22px" }}>{tab.icon}</span>
        <Flex vertical gap={0}>
          <span>{tab.label}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            {tab.hint}
          </Typography.Text>
        </Flex>
      </Flex>
    ) : (
      tab.label
    ),
  }));

  return (
    <>
      <PageHeader title="Cấu hình" />
      {wide ? (
        <Flex gap={28} align="flex-start">
          <div style={{ position: "sticky", top: 16, width: 240, flex: "none" }}>
            <Tabs
              tabPlacement="start"
              activeKey={active}
              items={items}
              onChange={(key) => router.push(key)}
              style={{ width: "100%" }}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
        </Flex>
      ) : (
        <>
          <Tabs activeKey={active} items={items} onChange={(key) => router.push(key)} style={{ marginTop: -8 }} />
          {children}
        </>
      )}
    </>
  );
}
