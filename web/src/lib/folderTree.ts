import type { MediaFolder } from "./api";

/**
 * A folder of the "Kho tư liệu" as a node of the tree drawn on every folder list: a folder is still only the path
 * kept on each item ("Gia/Lung"), each part before a "/" a parent. `own`: items right in this folder; `total`: those
 * and every folder below it. A parent no item sits right in (`Gia` of `Gia/Lung`) is a node with `own` 0. Choosing a
 * node filters on whole parts of the path, as the api does: `Gia` takes `Gia` and `Gia/…`, never `Gian/…`
 * (docs/decisions/2026-11-11-media-folder-tree.md).
 */
export type FolderNode = {
  path: string;
  name: string;
  own: number;
  total: number;
  topicId: number | null;
  topic: string | null;
  children: FolderNode[];
};

/** Whether an item in `folder` shows when `path` is chosen: the same folder or one below it. */
export function inFolder(folder: string, path: string): boolean {
  return folder === path || folder.startsWith(`${path}/`);
}

/** The parents of a path, outermost first: "A/B/C" has "A" and "A/B". */
export function ancestors(path: string): string[] {
  const parts = path.split("/");
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
}

/** The tree of the api's flat list of folders, each level sorted by name as people read it. */
export function buildFolderTree(folders: MediaFolder[]): FolderNode[] {
  const nodes = new Map<string, FolderNode>();
  const roots: FolderNode[] = [];
  const nodeOf = (path: string): FolderNode => {
    const found = nodes.get(path);
    if (found) return found;
    const node: FolderNode = {
      path,
      name: path.split("/").at(-1) ?? path,
      own: 0,
      total: 0,
      topicId: null,
      topic: null,
      children: [],
    };
    nodes.set(path, node);
    const parent = ancestors(path).at(-1);
    (parent === undefined ? roots : nodeOf(parent).children).push(node);
    return node;
  };
  for (const row of folders) {
    if (!row.folder) continue;
    const node = nodeOf(row.folder);
    node.own += row.count;
    node.topicId = row.topic_id;
    node.topic = row.topic;
    for (const path of [...ancestors(row.folder), row.folder]) nodeOf(path).total += row.count;
  }
  const sort = (list: FolderNode[]) => {
    list.sort((a, b) => a.name.localeCompare(b.name, "vi", { sensitivity: "base" }) || a.name.localeCompare(b.name));
    list.forEach((node) => sort(node.children));
  };
  sort(roots);
  return roots;
}

/** The node of a path, or undefined when no folder has it. */
export function findFolder(tree: FolderNode[], path: string): FolderNode | undefined {
  for (const node of tree) {
    if (node.path === path) return node;
    if (path.startsWith(`${node.path}/`)) return findFolder(node.children, path);
  }
  return undefined;
}
