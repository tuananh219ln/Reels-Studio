/** One line of a line-by-line comparison: kept, removed (only in the old text) or added (only in the new one). */
export type DiffLine = { kind: "same" | "removed" | "added"; text: string };

/** The old and new text line by line, through their longest common subsequence: what a prompt's "Xem khác biệt"
 * shows. Prompts are at most 20,000 characters, so the quadratic table stays small. */
export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  // common[i][j]: the longest common run of a[i..] and b[j..].
  const common = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ kind: "same", text: a[i] });
      i++;
      j++;
    } else if (common[i + 1][j] >= common[i][j + 1]) {
      lines.push({ kind: "removed", text: a[i++] });
    } else {
      lines.push({ kind: "added", text: b[j++] });
    }
  }
  a.slice(i).forEach((text) => lines.push({ kind: "removed", text }));
  b.slice(j).forEach((text) => lines.push({ kind: "added", text }));
  return lines;
}

/** How many lines were added and removed ("+12 −3 dòng"). */
export function diffCounts(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((line) => line.kind === "added").length,
    removed: lines.filter((line) => line.kind === "removed").length,
  };
}
