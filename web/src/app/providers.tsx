"use client";

import { App, ConfigProvider } from "antd";
import viVN from "antd/locale/vi_VN";
import { theme } from "./theme";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider theme={theme} locale={viVN}>
      <App>{children}</App>
    </ConfigProvider>
  );
}
