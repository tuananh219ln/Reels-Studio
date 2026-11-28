import type { CSSProperties } from "react";
import { COLORS } from "@/app/theme";

/** The phone's own header bar (AppShell), under which a detail page's header sticks. */
export const PHONE_HEADER = 60;

/**
 * The white bar a detail page (a video, a "Bài viết") holds at the top while it scrolls. It reaches the edges of the
 * content area, so its negative margins match AppShell's padding.
 */
export function detailHeaderStyle(desktop: boolean): CSSProperties {
  return {
    position: "sticky",
    top: desktop ? 0 : PHONE_HEADER,
    zIndex: 9,
    margin: desktop ? "-32px -32px 12px" : "-20px -16px 12px",
    padding: desktop ? "12px 32px 10px" : "8px 16px",
    background: COLORS.surface,
    borderBottom: `1px solid ${COLORS.border}`,
  };
}
