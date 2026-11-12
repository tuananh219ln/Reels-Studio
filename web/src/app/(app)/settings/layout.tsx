"use client";

import {
  ApiOutlined,
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

type Tab = { key: string; label: string; hint: string; icon: React.ReactNode };

/** The "Cài đặt" tabs, the member's own first, then the team's; each tab is its own page, so a link or a reload
 * opens the same tab. */
const GROUPS: { key: string; label: string; tabs: Tab[] }[] = [
  {
    key: "group:mine",
    label: "Của tôi",
    tabs: [
      {
        key: "/settings/defaults",
        label: "Thiết lập mặc định",
        hint: "Video mới của tôi",
        icon: <ControlOutlined />,
      },
      {
        key: "/settings/affiliate-accounts",
        label: "Tài khoản affiliate",
        hint: "Shopee, TikTok của tôi",
        icon: <ShoppingOutlined />,
      },
      { key: "/settings/mcp", label: "Kết nối MCP", hint: "ChatGPT, Claude của tôi", icon: <ApiOutlined /> },
    ],
  },
  {
    key: "group:team",
    label: "Chung cả nhóm",
    tabs: [
      { key: "/settings/ai", label: "Mô hình AI", hint: "AI viết kịch bản, giọng VieNeu", icon: <RobotOutlined /> },
      {
        key: "/settings/sources",
        label: "Nguồn tư liệu",
        hint: "Kho ảnh, ảnh AI, giọng ElevenLabs",
        icon: <PictureOutlined />,
      },
      { key: "/settings/templates", label: "Mẫu dựng", hint: "Thư viện mẫu của đội", icon: <ThunderboltOutlined /> },
      { key: "/settings/render-nodes", label: "Máy render", hint: "Chế độ render, các máy", icon: <DesktopOutlined /> },
    ],
  },
];
const TABS = GROUPS.flatMap((group) => group.tabs);

/** On a wide screen the tabs are a list down the left, each with a line on what it holds, beside the tab's page; on
 * a narrower one they are a row above it. A group's name heads its tabs, as a tab that cannot be chosen. */
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const wide = Grid.useBreakpoint().xl ?? false;
  const active = TABS.find((tab) => pathname.startsWith(tab.key))?.key ?? TABS[0].key;
  const items = GROUPS.flatMap((group) => [
    {
      key: group.key,
      disabled: true,
      label: (
        // A heading over its tabs, in plain grey: a coloured tag here read as a status.
        <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 600, cursor: "default" }}>
          {group.label}
        </Typography.Text>
      ),
    },
    ...group.tabs.map((tab) => ({
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
    })),
  ]);

  return (
    <>
      <PageHeader title="Cài đặt" />
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
