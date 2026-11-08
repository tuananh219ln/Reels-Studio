import type { SelectProps } from "antd";
import type { VideoDetail } from "./api";

type Page = VideoDetail["fanpages"][number];

/** A Page picker's options with the signed-in member's own Pages first, under "Trang của tôi", and the team's
 * others under "Trang khác" (brief part B2); flat when only one of the two kinds is there. */
export function pageOptions(pages: Page[], meId: number | undefined): NonNullable<SelectProps["options"]> {
  const option = (page: Page) => ({
    value: page.id,
    label: page.owner && page.owner_id !== meId ? `${page.name}, ${page.owner}` : page.name,
  });
  const mine = pages.filter((page) => meId !== undefined && page.owner_id === meId).map(option);
  const others = pages.filter((page) => meId === undefined || page.owner_id !== meId).map(option);
  if (mine.length === 0 || others.length === 0) {
    return [...mine, ...others];
  }
  return [
    { label: "Trang của tôi", title: "Trang của tôi", options: mine },
    { label: "Trang khác", title: "Trang khác", options: others },
  ];
}
