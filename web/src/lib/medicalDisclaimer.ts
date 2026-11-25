/**
 * The medical reminder of a health group's article moved from the caption to the last pinned comment (api
 * disclaimer.py, decisions 2026-11-25). This is its twin for the preview: the same rules, so the preview shows what
 * the worker posts. The caption stored in the database is never changed by it.
 */

const MAX_PARAGRAPH = 300;

function isReminder(paragraph: string, first: boolean): boolean {
  const text = paragraph.trim();
  if (text.startsWith("(*)")) return true;
  // The first paragraph is the hook (the text card's words): only "(*)" takes it away.
  if (first) return false;
  const lower = text.toLowerCase();
  return (
    text.length < MAX_PARAGRAPH &&
    lower.includes("tham khảo") &&
    ["bác sĩ", "y khoa", "chuyên gia"].some((word) => lower.includes(word))
  );
}

/** The caption without its reminder paragraphs, at most one blank line between the rest; unchanged if it has none. */
export function stripMedicalDisclaimer(caption: string): string {
  const paragraphs = caption.trim().split(/\n[ \t]*\n/);
  const filled = paragraphs.filter((paragraph) => paragraph.trim());
  const kept = paragraphs
    .map((paragraph, index) => ({ paragraph: paragraph.trim(), index }))
    .filter(({ paragraph, index }) => paragraph && !isReminder(paragraph, index === 0));
  return kept.length === filled.length ? caption.trim() : kept.map(({ paragraph }) => paragraph).join("\n\n");
}
