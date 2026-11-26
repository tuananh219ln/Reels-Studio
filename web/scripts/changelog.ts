/**
 * Writes public/changelog.json for "Có gì mới" (src/lib/changelog.ts) from the pull requests merged into main. The
 * deploy runs it before building the web app: `node scripts/changelog.ts`, with GITHUB_REPOSITORY, GITHUB_SHA and
 * GITHUB_TOKEN from GitHub Actions. Any failure writes nothing and exits 0: the deploy goes on without the window.
 */
import { writeFileSync } from "node:fs";
import path from "node:path";
import { buildEntries, type Changelog, MAX_ENTRIES, type MergedPull } from "../src/lib/changelog.ts";

const repo = process.env.GITHUB_REPOSITORY || "tuananh219ln/Reels-Studio";
const token = process.env.GITHUB_TOKEN;
const out = path.resolve(import.meta.dirname, "..", "public", "changelog.json");

async function mergedPulls(): Promise<MergedPull[]> {
  const pulls: MergedPull[] = [];
  // Closed PRs into main, most recently updated first; a few pages hold more than enough merged ones.
  for (let page = 1; page <= 3 && pulls.length < MAX_ENTRIES * 2; page += 1) {
    const response = await fetch(
      `https://api.github.com/repos/${repo}/pulls?state=closed&base=main&sort=updated&direction=desc&per_page=100&page=${page}`,
      {
        headers: {
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      },
    );
    if (!response.ok) throw new Error(`GitHub answered ${response.status}`);
    const batch = (await response.json()) as MergedPull[];
    pulls.push(...batch.filter((pull) => pull.merged_at));
    if (batch.length < 100) break;
  }
  return pulls;
}

try {
  const changelog: Changelog = {
    version: process.env.GITHUB_SHA || "local",
    generated_at: new Date().toISOString(),
    entries: buildEntries(await mergedPulls()),
  };
  writeFileSync(out, `${JSON.stringify(changelog, null, 2)}\n`);
  console.log(`changelog.json: ${changelog.entries.length} changes, version ${changelog.version}`);
} catch (err) {
  console.warn(`changelog.json not written: ${err instanceof Error ? err.message : String(err)}`);
}
