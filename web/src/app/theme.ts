import type { ThemeConfig } from "antd";

/**
 * The app's one palette, the orange of its icon (src/app/icon.svg). It is used the way the icon uses it: the
 * orange as a fill with white on it (primary buttons, the selected menu item), and a deeper orange of the same hue
 * wherever the brand colour is text or a thin mark on white (links, tabs, switches, checkboxes, focus), since the
 * icon's orange is too light for small text on white. Components take colours from here (or antd's tokens), never a
 * hex of their own.
 *
 * Orange is kept for two jobs only, the main action and where you are, so it still points at something. Everything
 * informational (a running job, a note, "processing") is a quiet slate blue, and statuses are a dot and a word
 * (StatusText), not a tinted tag.
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
  /** The selected menu item and other "you are here" fills: a grey a step darker than a hover. */
  selected: "#EEEFF1",
  /** Information that is not the brand: a running job, a note. */
  info: "#3B6A9A",
  infoBg: "#F1F5F9",
  infoBorder: "#CBD8E6",
} as const;

export const FONT_FAMILY = "var(--font-app), -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";

export const theme: ThemeConfig = {
  token: {
    colorPrimary: COLORS.primary,
    // Info (job banners, notes) is a quiet slate blue, so orange is left for the main action and the current place.
    colorInfo: COLORS.info,
    colorInfoBg: COLORS.infoBg,
    colorInfoBgHover: "#E6EDF5",
    colorInfoBorder: COLORS.infoBorder,
    colorInfoBorderHover: "#AFC4DA",
    colorInfoText: COLORS.info,
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
    // Cards are told apart by their border, not by a shadow.
    boxShadowTertiary: "none",
  },
  components: {
    Layout: { siderBg: COLORS.surface, headerBg: COLORS.surface, bodyBg: COLORS.layout },
    Menu: {
      // The selected item is a grey fill with the deep orange text: the place you are, without a block of colour.
      itemSelectedBg: COLORS.selected,
      itemSelectedColor: COLORS.primary,
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
      // Link buttons ("Mở tất cả", "Tùy chọn khác") are text: the deep orange.
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
