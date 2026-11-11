"use client";

import { FolderOutlined } from "@ant-design/icons";
import { TreeSelect, type TreeSelectProps } from "antd";
import { useMemo, useState } from "react";
import { plain } from "@/components/FilterSelect";
import type { MediaFolder } from "@/lib/api";
import { buildFolderTree, type FolderNode } from "@/lib/folderTree";

/** "Không thư mục" as a choice: the library's root. */
const NONE = "\u0000none";

/** A folder as typed, the way the api keeps it: no empty parts, single spaces, forward slashes. */
export function cleanFolder(raw: string): string {
  return raw
    .normalize("NFC")
    .replaceAll("\\", "/")
    .split("/")
    .map((part) => part.split(/\s+/).filter(Boolean).join(" "))
    .filter((part) => part && part !== "." && part !== "..")
    .join("/");
}

type TreeOption = {
  value: string;
  /** The line in the dropdown: the folder's own name (its last part), its count and its group. */
  title: string;
  /** What the box shows once chosen: the whole path. */
  label: string;
  disabled?: boolean;
  children?: TreeOption[];
};

/** A node's line: its own name, the items in it and below it, and the group whose "Tư liệu" it is. */
function nodeTitle(node: FolderNode): string {
  return `${node.name} (${node.total})${node.topic ? `, nhóm ${node.topic}` : ""}`;
}

function treeOptions(nodes: FolderNode[], forTopic?: number): TreeOption[] {
  return nodes.map((node) => ({
    value: node.path,
    title: nodeTitle(node),
    label: node.path,
    disabled: forTopic !== undefined && node.topicId !== null && node.topicId !== forTopic,
    children: node.children.length ? treeOptions(node.children, forTopic) : undefined,
  }));
}

function parents(nodes: FolderNode[]): string[] {
  return nodes.flatMap((node) => (node.children.length ? [node.path, ...parents(node.children)] : []));
}

/**
 * The folders as a tree, every parent open until the member closes it (docs/decisions/2026-11-11-media-folder-tree.md),
 * and a search that matches a folder's whole path without accents or case.
 */
function useFolderTree(folders: MediaFolder[], forTopic?: number) {
  const tree = useMemo(() => buildFolderTree(folders), [folders]);
  const options = useMemo(() => treeOptions(tree, forTopic), [tree, forTopic]);
  const allParents = useMemo(() => parents(tree), [tree]);
  const [closed, setClosed] = useState<string[]>([]);
  return {
    options,
    expand: {
      treeExpandedKeys: allParents.filter((path) => !closed.includes(path)),
      onTreeExpand: (keys: React.Key[]) => setClosed(allParents.filter((path) => !keys.includes(path))),
    },
  };
}

const matches = (input: string, node: { value?: unknown; title?: unknown }) =>
  plain(`${String(node.value ?? "")} ${String(node.title ?? "")}`).includes(plain(input));

/**
 * Every place a folder of the "Kho tư liệu" is chosen (adding items, "Chuyển thư mục", a group's "Tư liệu"): the
 * folders there as a tree with their counts (a parent counting everything below it), and typing a new name offers
 * "Tạo thư mục “…”", so a folder is picked rather than typed again slightly differently. A parent can be chosen like
 * any folder. `value` "" is "Không thư mục" when `allowNone`; null is nothing chosen. `forTopic`: a folder another
 * group links is shown but cannot be picked.
 */
export default function FolderSelect({
  folders,
  value,
  onChange,
  allowNone = false,
  forTopic,
  ...props
}: Omit<
  TreeSelectProps<string>,
  "value" | "onChange" | "treeData" | "showSearch" | "filterTreeNode" | "onSearch" | "searchValue"
> & {
  folders: MediaFolder[];
  value: string | null;
  onChange: (folder: string | null) => void;
  allowNone?: boolean;
  forTopic?: number;
}) {
  const { options, expand } = useFolderTree(folders, forTopic);
  const [typed, setTyped] = useState("");
  const name = cleanFolder(typed);
  const isNew = Boolean(name) && !folders.some((row) => row.folder === name);
  const treeData: TreeOption[] = [
    ...(isNew ? [{ value: name, title: `Tạo thư mục “${name}”`, label: name }] : []),
    ...(allowNone ? [{ value: NONE, title: "Không thư mục", label: "Không thư mục" }] : []),
    ...options,
  ];
  return (
    <TreeSelect<string>
      showSearch
      allowClear
      suffixIcon={<FolderOutlined />}
      placeholder="Chọn hoặc gõ tên thư mục mới…"
      notFoundContent="Gõ tên để tạo thư mục mới"
      treeNodeLabelProp="label"
      {...expand}
      {...props}
      value={value === null ? undefined : value === "" && allowNone ? NONE : value}
      searchValue={typed}
      onSearch={setTyped}
      // The "Tạo thư mục" line always shows while typing; the others match their path without accents or case.
      filterTreeNode={(input, node) => node.value === name || matches(input, node)}
      onChange={(next) => {
        setTyped("");
        onChange(next === undefined ? null : next === NONE ? "" : next);
      }}
      treeData={treeData}
    />
  );
}

/**
 * The folder filter of a list ("Mọi thư mục" when nothing is chosen): the same tree; choosing a parent shows what is
 * in it and in every folder below it.
 */
export function FolderFilter({
  folders,
  value,
  onChange,
  ...props
}: Omit<TreeSelectProps<string>, "value" | "onChange" | "treeData" | "showSearch" | "filterTreeNode"> & {
  folders: MediaFolder[];
  value: string | null;
  onChange: (folder: string | null) => void;
}) {
  const { options, expand } = useFolderTree(folders);
  return (
    <TreeSelect<string>
      showSearch
      allowClear
      placeholder="Mọi thư mục"
      treeNodeLabelProp="label"
      {...expand}
      {...props}
      value={value ?? undefined}
      filterTreeNode={(input, node) => matches(input, node)}
      onChange={(next) => onChange(next ?? null)}
      treeData={options}
    />
  );
}
