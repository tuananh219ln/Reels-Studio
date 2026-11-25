import type { VideoDetail } from "@/lib/api";

/**
 * The pinned comment is always the title, the scenes numbered from 1, then "Dòng khảo sát" (api pinned.py,
 * docs/decisions/2026-11-19-pinned-comment-fixed-shape.md). The api builds it for "Copy ghim" and the Page's comment;
 * this twin builds the live preview while the survey line is typed. Keep the two in step.
 */

/** Text as it reads: no *emphasis* marks, one Unicode form, single spaces. */
export function normalize(text: string): string {
  return text.replaceAll("*", "").normalize("NFC").replace(/\s+/g, " ").trim();
}

/** The name without the number the script put before it ("1. ", "2) ", "#4: ", "Cặp 5: "); only with a mark after
 * the number, so a name that starts with a number of its own ("5 loại rau") keeps it. */
export function stripIndex(name: string): string {
  return name.replace(/^\s*(?:#|cặp\s*|số\s*)?\d+\s*[.):\-–—]\s*/iu, "").trim();
}

/** Each content scene's name, in order: its text's first line without its number; an empty one is left out. */
function namesOf(video: Pick<VideoDetail, "scenes">): string[] {
  return video.scenes
    .map((scene) => stripIndex(scene.text.split(/\r?\n/).map(normalize).find(Boolean) ?? ""))
    .filter(Boolean);
}

/** The comment: the title, the scenes one per line, then the survey line; an empty part is left out. */
export function buildPinComment(survey: string, video: Pick<VideoDetail, "scenes" | "title_scene" | "topic">): string {
  const titleText = video.title_scene && normalize(video.title_scene.text) ? video.title_scene.text : video.topic;
  const items = namesOf(video)
    .map((name, index) => `${index + 1}. ${name}`)
    .join("\n");
  return [normalize(titleText), items, normalize(survey)].filter(Boolean).join("\n");
}
