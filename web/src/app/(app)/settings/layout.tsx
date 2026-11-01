"use client";

import { Tabs, Typography } from "antd";
import { usePathname, useRouter } from "next/navigation";

/** The "Cấu hình" tabs; each tab is its own page, so a link or a reload opens the same tab. */
const CONFIG_TABS = [
  { key: "/settings/defaults", label: "Thiết lập mặc định" },
  { key: "/settings/ai", label: "Mô hình AI" },
  { key: "/settings/sources", label: "Nguồn tư liệu" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const active = CONFIG_TABS.find((tab) => pathname.startsWith(tab.key))?.key ?? CONFIG_TABS[0].key;
  return (
    <>
      <Typography.Title level={2} style={{ margin: 0, fontWeight: 600 }}>
        Cấu hình
      </Typography.Title>
      <Tabs activeKey={active} items={CONFIG_TABS} onChange={(key) => router.push(key)} style={{ marginTop: 8 }} />
      {children}
    </>
  );
}
