"use client";

import type { MediaFolder } from "@/lib/api";
import { buildFolderTree, type FolderNode } from "@/lib/folderTree";
import { AppstoreOutlined, FolderOpenOutlined, FolderOutlined } from "@ant-design/icons";
import { Flex, Tree, Typography, theme, type TreeDataNode } from "antd";
import { useMemo, useState } from "react";

/** What a dragged tile carries: the ids of the items to move, as JSON. */
export const DRAG_TYPE = "application/x-media-ids";

type Node = TreeDataNode & { path: string; total: number };

function toNodes(nodes: FolderNode[]): Node[] {
  return nodes.map((node) => ({
    key: node.path,
    path: node.path,
    total: node.total,
    title: node.name,
    children: toNodes(node.children),
  }));
}

/**
 * The library's folders as a tree beside the grid ("Thư mục"): choosing a node shows it with everything below it, and
 * dropping tiles on a node moves them there (only their folder label changes). Every parent starts open
 * (docs/decisions/2026-11-11-media-folder-tree.md).
 */
export default function FolderSidebar({
  folders,
  total,
  value,
  onChange,
  onDropItems,
}: {
  folders: MediaFolder[];
  /** The whole library's count, for "Tất cả". */
  total: number;
  value: string | null;
  onChange: (folder: string | null) => void;
  onDropItems: (ids: number[], folder: string) => void;
}) {
  const { token } = theme.useToken();
  const data = useMemo(() => toNodes(buildFolderTree(folders)), [folders]);
  const parents = useMemo(() => {
    const out: string[] = [];
    const walk = (list: Node[]) =>
      list.forEach((node) => {
        if (node.children?.length) {
          out.push(node.path);
          walk(node.children as Node[]);
        }
      });
    walk(data);
    return out;
  }, [data]);
  const [closed, setClosed] = useState<string[]>([]);
  const [over, setOver] = useState<string | null>(null);

  const drop = (path: string) => ({
    onDragOver: (event: React.DragEvent) => {
      if (!event.dataTransfer.types.includes(DRAG_TYPE)) return;
      event.preventDefault();
      setOver(path);
    },
    onDragLeave: () => setOver((now) => (now === path ? null : now)),
    onDrop: (event: React.DragEvent) => {
      setOver(null);
      const raw = event.dataTransfer.getData(DRAG_TYPE);
      if (!raw) return;
      event.preventDefault();
      onDropItems(JSON.parse(raw) as number[], path);
    },
  });

  return (
    <nav aria-label="Cây thư mục" data-testid="media-folders">
      <Typography.Text type="secondary" style={{ fontSize: 12, padding: "0 8px", display: "block", marginBottom: 4 }}>
        THƯ MỤC
      </Typography.Text>
      <Flex
        align="center"
        gap={8}
        role="button"
        tabIndex={0}
        aria-pressed={value === null}
        onClick={() => onChange(null)}
        onKeyDown={(event) => event.key === "Enter" && onChange(null)}
        style={{
          padding: "4px 8px",
          borderRadius: token.borderRadiusSM,
          cursor: "pointer",
          background: value === null ? token.colorPrimaryBg : undefined,
          fontWeight: value === null ? 600 : undefined,
        }}
      >
        <AppstoreOutlined />
        <span style={{ flex: 1 }}>Tất cả</span>
        <Typography.Text type="secondary">{total}</Typography.Text>
      </Flex>
      <Tree<Node>
        blockNode
        showLine={false}
        treeData={data}
        selectedKeys={value ? [value] : []}
        expandedKeys={parents.filter((path) => !closed.includes(path))}
        onExpand={(keys) => setClosed(parents.filter((path) => !keys.includes(path)))}
        onSelect={(_, info) => onChange(info.selected ? info.node.path : null)}
        titleRender={(node) => (
          <Flex
            align="center"
            gap={6}
            {...drop(node.path)}
            style={{
              minWidth: 0,
              borderRadius: token.borderRadiusSM,
              outline: over === node.path ? `2px dashed ${token.colorPrimary}` : undefined,
            }}
          >
            {value === node.path ? <FolderOpenOutlined /> : <FolderOutlined />}
            <Typography.Text ellipsis={{ tooltip: node.path }} style={{ flex: 1, color: "inherit" }}>
              {node.title as string}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {node.total}
            </Typography.Text>
          </Flex>
        )}
        style={{ background: "transparent" }}
      />
    </nav>
  );
}
