import type { ThemeConfig } from "antd";

export const TEAL = "#0F3B4C";
export const LOGO_GREEN = "#8BD450";

export const theme: ThemeConfig = {
  token: {
    colorPrimary: TEAL,
    colorLink: TEAL,
    colorBgLayout: "#F7F7F7",
    colorBorderSecondary: "#EDEDED",
    borderRadius: 6,
    fontFamily: "-apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
  components: {
    Menu: {
      itemSelectedBg: TEAL,
      itemSelectedColor: "#FFFFFF",
      itemBorderRadius: 8,
      itemHeight: 40,
      activeBarBorderWidth: 0,
    },
    Layout: { siderBg: "#FFFFFF", headerBg: "#FFFFFF", bodyBg: "#F7F7F7" },
    Calendar: { itemActiveBg: "#F7F7F7" },
  },
};
