import type { VideoDetail } from "@/lib/api";

/**
 * The pinned comment is a template (api pinned.py, docs/decisions/2026-11-14-pinned-comment-template.md): `{title}`,
 * `{items}`... are filled from the video's title and scenes as they are now. The api renders it for "Copy ghim" and
 * the Page's comment; this twin renders the live preview while the template is typed. Keep the two in step.
 */

/** The variables a template may name, with what "Chèn biến" calls them. */
export const PINNED_VARIABLES = [
  { name: "title", label: "Tiêu đề" },
  { name: "items", label: "Danh sách cảnh" },
  { name: "item_names", label: "Tên các món" },
  { name: "count", label: "Số cảnh" },
  { name: "hook", label: "Lời mở đầu" },
  { name: "products", label: "Sản phẩm" },
] as const;

const ITEM_VARIABLES = ["items", "item_names"];

/** Text as it reads: no *emphasis* marks, one Unicode form, single spaces. */
export function normalize(text: string): string {
  return text.replaceAll("*", "").normalize("NFC").replace(/\s+/g, " ").trim();
}

type Item = { order: number; name: string; benefit: string };

function itemsOf(video: Pick<VideoDetail, "scenes">): Item[] {
  const items: Item[] = [];
  for (const scene of video.scenes) {
    const lines = scene.text.split(/\r?\n/).map(normalize).filter(Boolean);
    if (lines.length > 0) {
      items.push({ order: items.length + 1, name: lines[0], benefit: lines.slice(1).join(" ") });
    }
  }
  return items;
}

/** The template with its variables filled from the video; an unknown `{name}` stays as typed. */
export function renderPinned(
  template: string,
  video: Pick<VideoDetail, "scenes" | "title_scene" | "topic" | "pinned_products">,
): string {
  const titleText = video.title_scene && normalize(video.title_scene.text) ? video.title_scene.text : video.topic;
  const title = normalize(titleText);
  const items = itemsOf(video);
  const values: Record<string, string> = {
    title,
    hook: normalize(video.title_scene?.voice_text ?? "") || title,
    count: String(items.length),
    items: items.map((item) => `${item.order}. ${item.name}` + (item.benefit ? ` – ${item.benefit}` : "")).join("\n"),
    item_names: items.map((item) => item.name).join(", "),
    products: video.pinned_products.map(normalize).join("\n"),
  };
  return template
    .replace(/\{(\w+)\}/g, (match, name: string) => (Object.hasOwn(values, name) ? values[name] : match))
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Whether the template still lists the scenes, so editing them changes the comment. */
export function followsScenes(template: string): boolean {
  return [...template.matchAll(/\{(\w+)\}/g)].some((match) => ITEM_VARIABLES.includes(match[1]));
}
