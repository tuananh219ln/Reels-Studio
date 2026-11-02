import type { ThemeConfig } from "antd";

/**
 * The app's one palette, the orange of its icon (src/app/icon.svg). It is used the way the icon uses it: the
 * orange as a fill with white on it (primary buttons, the selected menu item), and a deeper orange of the same hue
 * wherever the brand colour is text or a thin mark on white (links, tabs, switches, checkboxes, focus), since the
 * icon's orange is too light for small text on white. Components take colours from here (or antd's tokens), never a
 * hex of their own.
 */
export const COLORS = {
  /** The brand as text or a thin mark on white: about 5:1 against white. */
  primary: "#C2410C",
  /** The brand as a fill, white on it: the middle of the icon's gradient. */
  brand: "#F5551F",
  brandHover: "#FF6B35",
  brandActive: "#DC4815",
  brandInk: "#FFFFFF",
  /** A selected card, an active row, a drop zone being dragged over. */
  primaryBg: "#FFF2EB",
  primaryBorder: "#FDBB98",
  text: "#1F2328",
  textSecondary: "#5F6670",
  border: "#E7E8EA",
  /** The page behind cards and the side panel. */
  layout: "#F6F6F7",
  surface: "#FFFFFF",
  /** An empty or inactive area inside a card (no photo yet, an empty timeline segment). */
  muted: "#F8F8F9",
} as const;

export const FONT_FAMILY = "var(--font-app), -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";

export const theme: ThemeConfig = {
  token: {
    colorPrimary: COLORS.primary,
    // Info (job banners, "processing" tags) follows the brand, not antd's default blue.
    colorInfo: COLORS.primary,
    colorInfoBg: COLORS.primaryBg,
    colorInfoBgHover: "#FFE6D8",
    colorInfoBorder: COLORS.primaryBorder,
    colorInfoBorderHover: "#FB9E6E",
    colorInfoText: COLORS.primary,
    colorLink: COLORS.primary,
    colorText: COLORS.text,
    colorTextSecondary: COLORS.textSecondary,
    colorBgLayout: COLORS.layout,
    colorBorder: "#D9DBDF",
    colorBorderSecondary: COLORS.border,
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,
    controlHeight: 36,
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    boxShadowTertiary: "0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 6px -1px rgba(16, 24, 40, 0.04)",
  },
  components: {
    Layout: { siderBg: COLORS.surface, headerBg: COLORS.surface, bodyBg: COLORS.layout },
    Menu: {
      // The selected item looks like the icon: its orange, white on it.
      itemSelectedBg: COLORS.brand,
      itemSelectedColor: COLORS.brandInk,
      itemBorderRadius: 8,
      itemHeight: 40,
      activeBarBorderWidth: 0,
      // Submenus sit on the sider's own white, indented, not in a grey block.
      subMenuItemBg: "transparent",
      itemHoverBg: COLORS.muted,
    },
    Button: {
      fontWeight: 500,
      primaryShadow: "none",
      defaultShadow: "none",
      dangerShadow: "none",
      // Primary buttons are filled with the icon's orange, labelled in white.
      colorPrimary: COLORS.brand,
      colorPrimaryHover: COLORS.brandHover,
      colorPrimaryActive: COLORS.brandActive,
      primaryColor: COLORS.brandInk,
      // Default buttons turn the readable deep orange on hover.
      defaultHoverColor: COLORS.primary,
      defaultHoverBorderColor: COLORS.primary,
      defaultActiveColor: COLORS.primary,
      defaultActiveBorderColor: COLORS.primary,
      // Link buttons ("Mở tất cả", "Giữ ảnh này") are text: the deep orange.
      colorLink: COLORS.primary,
    },
    Card: { headerFontSize: 15, headerHeight: 52 },
    Tabs: { titleFontSize: 14, horizontalItemGutter: 24 },
    Table: { headerBg: COLORS.muted, headerColor: COLORS.textSecondary, headerSplitColor: "transparent" },
    Tag: { defaultBg: COLORS.muted },
    Segmented: { itemSelectedColor: COLORS.primary },
    Modal: { titleFontSize: 17 },
    Drawer: { footerPaddingBlock: 12 },
    Calendar: { itemActiveBg: COLORS.layout },
    // Collapsible groups (Kho kiến thức, Mô hình AI) read as white cards, like every other card.
    Collapse: { headerBg: COLORS.surface, contentBg: COLORS.surface },
  },
};
