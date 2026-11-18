import type { CommentLinks } from "@/lib/api";

/** How one post's link state reads: a colour (success, warning or none) and words for a dot's label. */
export const LINK_STATES: Record<CommentLinks, { tone: "success" | "warning" | "idle"; label: string }> = {
  yes: { tone: "success", label: "bình luận có link" },
  updating: { tone: "warning", label: "đang cập nhật link vào bình luận" },
  missing: { tone: "warning", label: "đã bình luận, thiếu link" },
  none: { tone: "idle", label: "chưa bình luận" },
  unknown: { tone: "idle", label: "chưa rõ có link chưa" },
  off: { tone: "idle", label: "" },
};

/** A post still lacking a link in its comments on Facebook: the "Thiếu link" tab. */
export function lacksLink(links: CommentLinks): boolean {
  return links === "missing" || links === "updating" || links === "none";
}

/** The least done of several posts' states, for a chip that stands for several Pages. */
export function worstLinks(states: CommentLinks[]): CommentLinks {
  const order: CommentLinks[] = ["missing", "none", "updating", "unknown", "yes", "off"];
  return order.find((state) => states.includes(state)) ?? "off";
}

/** One line for a video's Facebook posts: green when every Page has a link, yellow while one lacks it. */
export function linksSummary(states: CommentLinks[]): { label: string; tone: "success" | "warning" | "idle" } {
  const facebook = states.filter((state) => state !== "off");
  const yes = facebook.filter((state) => state === "yes").length;
  if (facebook.length === 0) {
    return { label: "Gắn giỏ trong app TikTok", tone: "idle" };
  }
  if (yes === facebook.length) {
    return { label: facebook.length > 1 ? `Có link · ${yes}/${facebook.length} Page` : "Có link", tone: "success" };
  }
  if (yes > 0) {
    return { label: `${yes}/${facebook.length} Page có link`, tone: "warning" };
  }
  if (facebook.includes("missing")) {
    return { label: "Đã bình luận, thiếu link", tone: "warning" };
  }
  if (facebook.includes("updating")) {
    return { label: "Đang cập nhật link", tone: "warning" };
  }
  if (facebook.includes("none")) {
    return { label: "Chưa bình luận", tone: "idle" };
  }
  return { label: "Chưa rõ", tone: "idle" };
}
