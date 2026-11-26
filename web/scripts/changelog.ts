/**
 * Writes public/changelog.json for "Có gì mới" (src/lib/changelog.ts) from the pull requests merged into main. The
 * deploy runs it before building the web app: `node scripts/changelog.ts`, with GITHUB_REPOSITORY, GITHUB_SHA and
 * GITHUB_TOKEN from GitHub Actions. Any failure writes nothing and exits 0: the deploy goes on without the window.
 */
import { writeFileSync } from "node:fs";
import path from "node:path";
import {
  buildEntries,
  type Changelog,
  type ChangeEntry,
  guidesFromFiles,
  MAX_ENTRIES,
  type MergedPull,
  type PullFile,
} from "../src/lib/changelog.ts";

const repo = process.env.GITHUB_REPOSITORY || "tuananh219ln/Reels-Studio";
const token = process.env.GITHUB_TOKEN;
const out = path.resolve(import.meta.dirname, "..", "public", "changelog.json");

const headers = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
};

async function get<T>(pathAndQuery: string): Promise<T> {
  const response = await fetch(`https://api.github.com/repos/${repo}/${pathAndQuery}`, { headers });
  if (!response.ok) throw new Error(`GitHub answered ${response.status} for ${pathAndQuery}`);
  return (await response.json()) as T;
}

async function mergedPulls(): Promise<MergedPull[]> {
  const pulls: MergedPull[] = [];
  // Closed PRs into main, most recently updated first; a few pages hold more than enough merged ones.
  for (let page = 1; page <= 3 && pulls.length < MAX_ENTRIES * 2; page += 1) {
    const batch = await get<MergedPull[]>(
      `pulls?state=closed&base=main&sort=updated&direction=desc&per_page=100&page=${page}`,
    );
    pulls.push(...batch.filter((pull) => pull.merged_at));
    if (batch.length < 100) break;
  }
  return pulls;
}

/** "Xem hướng dẫn": the guides each change's PR added or changed. A PR whose files cannot be read just has none. */
async function withGuides(entries: ChangeEntry[]): Promise<ChangeEntry[]> {
  return Promise.all(
    entries.map(async (entry) => {
      const files = await get<PullFile[]>(`pulls/${entry.number}/files?per_page=100`).catch(() => []);
      return { ...entry, guides: guidesFromFiles(files) };
    }),
  );
}

try {
  const changelog: Changelog = {
    version: process.env.GITHUB_SHA || "local",
    generated_at: new Date().toISOString(),
    entries: await withGuides(buildEntries(await mergedPulls())),
  };
  writeFileSync(out, `${JSON.stringify(changelog, null, 2)}\n`);
  console.log(`changelog.json: ${changelog.entries.length} changes, version ${changelog.version}`);
} catch (err) {
  console.warn(`changelog.json not written: ${err instanceof Error ? err.message : String(err)}`);
}
