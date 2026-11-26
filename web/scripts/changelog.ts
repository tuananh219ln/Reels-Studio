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
  type DeployRun,
  deployTimes,
  guidesFromFiles,
  MAX_ENTRIES,
  type MergedPull,
  pagesFromFiles,
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

/** "Xem hướng dẫn" and "Thử ngay": the guides and screens each change's PR touched. A PR whose files cannot be read has
 * neither. */
async function withFiles(entries: ChangeEntry[]): Promise<ChangeEntry[]> {
  return Promise.all(
    entries.map(async (entry) => {
      const files = await get<PullFile[]>(`pulls/${entry.number}/files?per_page=100`).catch(() => []);
      return { ...entry, guides: guidesFromFiles(files), pages: pagesFromFiles(files) };
    }),
  );
}

/** The deploys that went live: successful runs of this workflow for pushes to main. None when they cannot be read, and
 * every change then counts as part of this deploy. */
async function deployRuns(): Promise<DeployRun[]> {
  const answer = await get<{ workflow_runs: DeployRun[] }>(
    "actions/workflows/ci-cd.yml/runs?branch=main&event=push&status=success&per_page=100",
  ).catch(() => ({ workflow_runs: [] }));
  return answer.workflow_runs;
}

try {
  const generatedAt = new Date().toISOString();
  const entries = await withFiles(buildEntries(await mergedPulls()));
  const changelog: Changelog = {
    version: process.env.GITHUB_SHA || "local",
    generated_at: generatedAt,
    entries: deployTimes(entries, await deployRuns(), generatedAt),
  };
  writeFileSync(out, `${JSON.stringify(changelog, null, 2)}\n`);
  console.log(`changelog.json: ${changelog.entries.length} changes, version ${changelog.version}`);
} catch (err) {
  console.warn(`changelog.json not written: ${err instanceof Error ? err.message : String(err)}`);
}
