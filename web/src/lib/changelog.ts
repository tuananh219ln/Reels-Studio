/**
 * "Có gì mới" (docs/decisions/2026-11-26-whats-new.md): the changes merged into main, read from GitHub by the deploy
 * (scripts/changelog.ts) into public/changelog.json, and shown in the app. Nobody writes a changelog: a PR whose title
 * starts with feat, fix or perf is a change for members; the title after the colon is its headline and the first
 * paragraph of "Làm gì và vì sao" its detail. Everything else (chore, docs, test, ci, refactor) is left out.
 *
 * No imports and only plain TypeScript, so Node runs this file as it is in the deploy.
 */

export type ChangeKind = "feature" | "fix" | "improvement";

export type ChangeEntry = {
  number: number;
  kind: ChangeKind;
  title: string;
  summary: string;
  merged_at: string;
  url: string;
  /** The in-app guides (api/src/reels_api/guides) the PR added or changed: "Xem hướng dẫn" links to them. */
  guides: string[];
  /** "Thử ngay": the screens the PR changed (at most two; a change across more is not one place to try). */
  pages: string[];
  /** When the deploy that brought it went live; changes are grouped by it. Missing in a file written before. */
  deployed_at?: string;
};

/** What the deploy writes: `version` is the commit deployed, so an open tab can tell a newer one went live. */
export type Changelog = { version: string; generated_at: string; entries: ChangeEntry[] };

/** One merged pull request as GitHub's REST API lists it (only the fields read here). */
export type MergedPull = {
  number: number;
  title: string;
  body: string | null;
  merged_at: string | null;
  html_url: string;
};

export const KIND_LABEL: Record<ChangeKind, string> = {
  feature: "Tính năng mới",
  fix: "Sửa lỗi",
  improvement: "Cải thiện",
};

/** How many changes the file keeps; older ones drop off. */
export const MAX_ENTRIES = 60;
/** The detail is a sentence or two, cut at a word. */
const SUMMARY_LIMIT = 280;
/** A member who has never closed the window sees the changes of the last few days as new, not the whole history. */
export const FIRST_LOOK_DAYS = 3;

const TYPES: Record<string, ChangeKind> = { feat: "feature", fix: "fix", perf: "improvement" };

/** "feat(video): MP4 tải lên" → feature, "MP4 tải lên"; null for any other type or a title without one. */
export function parseTitle(title: string): { kind: ChangeKind; headline: string } | null {
  const match = title.trim().match(/^(\w+)(?:\([^)]*\))?!?:\s*(.+)$/);
  const kind = match ? TYPES[match[1].toLowerCase()] : undefined;
  if (!match || !kind) return null;
  const headline = match[2].trim();
  return { kind, headline: headline.charAt(0).toLocaleUpperCase("vi-VN") + headline.slice(1) };
}

/** Markdown and HTML comments out, so the detail reads as plain text. */
function plain(text: string): string {
  return text
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/(\*\*|__|`)/g, "")
    .replace(/\\(.)/g, "$1")
    .replace(/^\s*(?:[-*+]|\d+\.)\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** The first paragraph under "## Làm gì và vì sao" (or the body's first one when there is no such heading). */
export function summarize(body: string | null): string {
  if (!body) return "";
  const text = body.replace(/\r\n/g, "\n").replace(/<!--[\s\S]*?-->/g, "");
  const section = text.match(/^##\s*Làm gì và vì sao\s*$([\s\S]*?)(?=^##\s|(?![\s\S]))/m);
  const source = section ? section[1] : text;
  const paragraph =
    source
      .split(/\n\s*\n/)
      .map((part) => part.trim())
      .find((part) => part && !part.startsWith("#") && !/^_Requested by/.test(part)) ?? "";
  const clean = plain(paragraph);
  // "Ba việc cùng một PR:" only leads into a list: no detail is better than half a sentence.
  if (clean.endsWith(":")) return "";
  if (clean.length <= SUMMARY_LIMIT) return clean;
  const cut = clean.slice(0, SUMMARY_LIMIT);
  return `${cut.slice(0, cut.lastIndexOf(" ") > 0 ? cut.lastIndexOf(" ") : SUMMARY_LIMIT).replace(/[,.;:]$/, "")}…`;
}

/** The merged pull requests as the app shows them, newest first. */
export function buildEntries(pulls: MergedPull[]): ChangeEntry[] {
  const entries: ChangeEntry[] = [];
  for (const pull of pulls) {
    const parsed = pull.merged_at ? parseTitle(pull.title) : null;
    if (!parsed || !pull.merged_at) continue;
    entries.push({
      number: pull.number,
      kind: parsed.kind,
      title: parsed.headline,
      summary: summarize(pull.body),
      merged_at: pull.merged_at,
      url: pull.html_url,
      guides: [],
      pages: [],
    });
  }
  entries.sort((a, b) => b.merged_at.localeCompare(a.merged_at));
  return entries.slice(0, MAX_ENTRIES);
}

/** A PR's changed files as GitHub lists them (only the fields read here). */
export type PullFile = { filename: string; status: string };

/** The in-app guides a PR added or changed (a removed one has nothing to open), by slug. */
export function guidesFromFiles(files: PullFile[]): string[] {
  const slugs: string[] = [];
  for (const file of files) {
    const match = file.filename.match(/^api\/src\/reels_api\/guides\/([a-z0-9-]+)\.md$/);
    if (match && file.status !== "removed" && !slugs.includes(match[1])) slugs.push(match[1]);
  }
  return slugs;
}

/** The screens behind the login, by their folder in web/src/app/(app): the path and its name in the menu. */
export const SCREENS: Record<string, string> = {
  videos: "Video",
  articles: "Bài viết",
  posts: "Bài đăng",
  stats: "Thống kê",
  fanpages: "Quản lý kênh",
  affiliate: "Affiliate",
  knowledge: "Kho kiến thức",
  guides: "Tất cả hướng dẫn",
  media: "Kho tư liệu",
  music: "Thư viện nhạc",
  competitors: "Phân tích đối thủ",
  users: "Quản lý người dùng",
  jobs: "Nhật ký job",
  settings: "Cài đặt",
  "whats-new": "Có gì mới",
};
const MAX_PAGES = 2;

/** "Thử ngay": the screens whose own folder the PR changed, as paths ("/videos"); none when it changed more than two. */
export function pagesFromFiles(files: PullFile[]): string[] {
  const pages: string[] = [];
  for (const file of files) {
    const match = file.filename.match(/^web\/src\/app\/\(app\)\/([a-z0-9-]+)\//);
    if (match && SCREENS[match[1]] && file.status !== "removed" && !pages.includes(`/${match[1]}`)) {
      pages.push(`/${match[1]}`);
    }
  }
  return pages.length > MAX_PAGES ? [] : pages;
}

/** A successful run of the CI/CD workflow on main: it deployed when it finished. */
export type DeployRun = { created_at: string; updated_at: string };

/** When each change went live: the end of the first successful deploy started at or after its merge (a few seconds
 * of clock difference allowed); `now` for the deploy running at the moment, which has not finished yet. */
export function deployTimes(entries: ChangeEntry[], runs: DeployRun[], now: string): ChangeEntry[] {
  const sorted = [...runs].sort((a, b) => a.created_at.localeCompare(b.created_at));
  return entries.map((entry) => {
    const from = Date.parse(entry.merged_at) - 5_000;
    const run = sorted.find((one) => Date.parse(one.created_at) >= from);
    return { ...entry, deployed_at: run ? run.updated_at : now };
  });
}

/** The changes in groups, one per deploy, newest first; a file without deploy times is one group. */
export function byDeploy(entries: ChangeEntry[]): { deployed_at: string | null; entries: ChangeEntry[] }[] {
  const groups: { deployed_at: string | null; entries: ChangeEntry[] }[] = [];
  const sorted = [...entries].sort(
    (a, b) => (b.deployed_at ?? "").localeCompare(a.deployed_at ?? "") || b.merged_at.localeCompare(a.merged_at),
  );
  for (const entry of sorted) {
    const at = entry.deployed_at ?? null;
    const last = groups[groups.length - 1];
    if (last && last.deployed_at === at) last.entries.push(entry);
    else groups.push({ deployed_at: at, entries: [entry] });
  }
  return groups;
}

/** The changes the deploy that wrote the file brought (deployed "now", when it was written). */
export function thisDeploy(changelog: Changelog): ChangeEntry[] {
  return changelog.entries.filter((entry) => entry.deployed_at === changelog.generated_at);
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** The Telegram message for the team's group after a deploy (HTML parse mode); null when it brought nothing new. */
export function telegramMessage(changelog: Changelog, webUrl = ""): string | null {
  const entries = thisDeploy(changelog);
  if (entries.length === 0) return null;
  const lines = ["<b>Reels Studio vừa cập nhật</b>", ""];
  for (const entry of entries) {
    lines.push(`• <b>${escapeHtml(entry.title)}</b> (${KIND_LABEL[entry.kind]})`);
    if (entry.summary) lines.push(escapeHtml(entry.summary));
  }
  const base = webUrl.replace(/\/$/, "");
  if (base) lines.push("", `<a href="${escapeHtml(base)}/whats-new">Xem trong app</a>`);
  return lines.join("\n");
}

/** The newest changelog.json, never from a cache; null where the deploy wrote none (development, E2E). */
export async function readChangelog(): Promise<Changelog | null> {
  const response = await fetch(`/changelog.json?t=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) return null;
  const data = (await response.json()) as Changelog;
  return Array.isArray(data.entries) ? data : null;
}

/** The changes a member has not seen: merged after their mark, or in the last few days when they have none. */
export function unseenEntries(entries: ChangeEntry[], seenAt: string | null, now = Date.now()): ChangeEntry[] {
  const after = seenAt ? Date.parse(seenAt) : now - FIRST_LOOK_DAYS * 24 * 3600 * 1000;
  return entries.filter((entry) => Date.parse(entry.merged_at) > after);
}
