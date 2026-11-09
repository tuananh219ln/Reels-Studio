import type { SelectProps } from "antd";
import type { VideoDetail } from "./api";

type Page = VideoDetail["fanpages"][number];

/** The Pages the signed-in member may post to: only their own, as a post's commission is its Page's owner's
 * (docs/decisions/2026-11-09-page-owner-posts.md). A teammate's Page is not offered. */
export function myPages(pages: Page[], meId: number | undefined): Page[] {
  return pages.filter((page) => meId !== undefined && page.owner_id === meId);
}

/** A Page picker's options: the member's own Pages. */
export function pageOptions(pages: Page[], meId: number | undefined): NonNullable<SelectProps["options"]> {
  return myPages(pages, meId).map((page) => ({ value: page.id, label: page.name }));
}

/** Said where a member has no Page of their own to post to. */
export const NO_PAGE_OF_MINE =
  "Bạn chưa có Fanpage nào. Chỉ chủ Page mới đăng lên Page đó: vào Quản lý Page để thêm Page của bạn, hoặc bấm “Nhận Page” với Page chưa có chủ.";
