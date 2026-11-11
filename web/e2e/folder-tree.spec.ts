// The folder tree of the "Kho tư liệu" built from the api's flat list of folders (src/lib/folderTree.ts): pure
// functions, so these tests open no page (docs/decisions/2026-11-11-media-folder-tree.md).
import { expect, test } from "@playwright/test";
import { ancestors, buildFolderTree, findFolder, inFolder, type FolderNode } from "../src/lib/folderTree";

const folder = (name: string, count: number, topic: string | null = null, topicId: number | null = null) => ({
  folder: name,
  count,
  topic,
  topic_id: topicId,
});

/** The tree as "path (total)" lines, indented by depth, to compare whole trees at a glance. */
function lines(nodes: FolderNode[], depth = 0): string[] {
  return nodes.flatMap((node) => [
    `${"  ".repeat(depth)}${node.name} (${node.total})`,
    ...lines(node.children, depth + 1),
  ]);
}

test("the production Già folders make one parent with eight children and their counts", () => {
  const tree = buildFolderTree([
    folder("Gia/Co vai gay", 8),
    folder("Gia/Di bo", 2),
    folder("Gia/Giac ngu", 8),
    folder("Gia/Goi khop", 10),
    folder("Gia/Khop tay", 2),
    folder("Gia/Lung", 6),
    folder("Gia/Thang bang", 4),
    folder("Gia/Tri nho", 2),
  ]);
  expect(lines(tree)).toEqual([
    "Gia (42)",
    "  Co vai gay (8)",
    "  Di bo (2)",
    "  Giac ngu (8)",
    "  Goi khop (10)",
    "  Khop tay (2)",
    "  Lung (6)",
    "  Thang bang (4)",
    "  Tri nho (2)",
  ]);
  expect(tree[0].path).toBe("Gia");
  expect(tree[0].own).toBe(0);
  expect(tree[0].children.map((node) => node.path)).toContain("Gia/Thang bang");
});

test("a folder with no slash is a node of its own, and items right in a parent count towards it", () => {
  const tree = buildFolderTree([folder("Máy xay", 3), folder("Gia", 2), folder("Gia/Lung", 6)]);
  expect(lines(tree)).toEqual(["Gia (8)", "  Lung (6)", "Máy xay (3)"]);
  expect(findFolder(tree, "Gia")?.own).toBe(2);
  expect(findFolder(tree, "Máy xay")?.children).toEqual([]);
});

test("any depth: a grandchild three levels down adds to every parent above it", () => {
  const tree = buildFolderTree([folder("A/B/C", 3), folder("A/B", 1), folder("A/D", 2)]);
  expect(lines(tree)).toEqual(["A (6)", "  B (4)", "    C (3)", "  D (2)"]);
  expect(findFolder(tree, "A/B/C")?.name).toBe("C");
  expect(ancestors("A/B/C")).toEqual(["A", "A/B"]);
  expect(ancestors("A")).toEqual([]);
});

test("a parent never takes in a folder that only starts with the same letters", () => {
  const tree = buildFolderTree([folder("Gia/Lung", 6), folder("Gian/Bep", 3), folder("Gian", 1)]);
  expect(lines(tree)).toEqual(["Gia (6)", "  Lung (6)", "Gian (4)", "  Bep (3)"]);
  expect(inFolder("Gia/Lung", "Gia")).toBe(true);
  expect(inFolder("Gia", "Gia")).toBe(true);
  expect(inFolder("Gian/Bep", "Gia")).toBe(false);
  expect(inFolder("Gian", "Gia")).toBe(false);
  expect(inFolder("Gia/Lung/Tren", "Gia/Lung")).toBe(true);
  expect(inFolder("Gia/Lungo", "Gia/Lung")).toBe(false);
});

test("a folder a group links keeps its group, and a linked parent with nothing in it yet still shows", () => {
  const tree = buildFolderTree([folder("Gia", 0, "Già Mà Khỏe", 7), folder("Gia/Lung", 6)]);
  const parent = findFolder(tree, "Gia");
  expect(parent).toMatchObject({ own: 0, total: 6, topic: "Già Mà Khỏe", topicId: 7 });
  expect(findFolder(tree, "Gia/Lung")?.topic).toBeNull();
});
