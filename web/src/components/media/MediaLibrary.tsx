"use client";

import { useMe } from "@/components/MeContext";
import FolderActions from "@/components/media/FolderActions";
import FolderSidebar, { DRAG_TYPE } from "@/components/media/FolderSidebar";
import { FolderFilter } from "@/components/media/FolderSelect";
import MediaDetailDrawer from "@/components/media/MediaDetailDrawer";
import MediaGrid, { type TileSize } from "@/components/media/MediaGrid";
import MediaUploadCard from "@/components/media/MediaUploadCard";
import MoveFolderModal from "@/components/media/MoveFolderModal";
import TagEditModal, { type TagEdit } from "@/components/media/TagEditModal";
import TagSelect from "@/components/media/TagSelect";
import PageHeader from "@/components/PageHeader";
import { api, errorMessage, type MediaItem, type MediaList } from "@/lib/api";
import { inFolder } from "@/lib/folderTree";
import { useUrlChoiceIf } from "@/lib/urlState";
import { DeleteOutlined, FolderOutlined, PlusOutlined, SearchOutlined, TagsOutlined } from "@ant-design/icons";
import { App, Button, Card, Drawer, Flex, Grid, Input, Popconfirm, Segmented, Tooltip, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

/** The tile size, kept per browser. */
function useTileSize(): [TileSize, (next: TileSize) => void] {
  const [size, setSize] = useState<TileSize>(() => {
    try {
      const saved = typeof window === "undefined" ? null : window.localStorage.getItem("media-tile-size");
      return saved === "s" || saved === "m" || saved === "l" ? saved : "m";
    } catch {
      return "m"; // Storage blocked: the default size.
    }
  });
  return [
    size,
    (next) => {
      setSize(next);
      try {
        window.localStorage.setItem("media-tile-size", next);
      } catch {
        // Not kept; the choice still holds for this visit.
      }
    },
  ];
}

export default function MediaLibrary({
  lockedFolder,
  embedded = false,
  onChanged,
  showUpload = true,
  keyword,
}: {
  lockedFolder?: string;
  embedded?: boolean;
  showUpload?: boolean;
  keyword?: string;
  onChanged?: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const { me } = useMe();
  const [data, setData] = useState<MediaList>({ items: [], folders: [], tags: [], total: 0 });
  const [shown, setShown] = useUrlChoiceIf<string | null>(!embedded, "folder", lockedFolder ?? null);
  const [kind, setKind] = useUrlChoiceIf<"all" | "photo" | "clip">(!embedded, "kind", "all", ["photo", "clip"]);
  const [query, setQuery] = useUrlChoiceIf<string>(!embedded, "q", "");
  // The tag filter: items carrying every tag chosen, kept in the address as "xoay-co,sofa".
  const [tagText, setTagText] = useUrlChoiceIf<string>(!embedded, "tags", "");
  const tags = tagText ? tagText.split(",").filter(Boolean) : [];
  const [tagEdit, setTagEdit] = useState<TagEdit | null>(null);
  // Items chosen for "Chuyển thư mục" on several at once, and what the dialog moves (one item or the chosen ones).
  const [selected, setSelected] = useState<number[]>([]);
  const [moving, setMoving] = useState<{ ids: number[]; current?: string }>({ ids: [] });
  // The page lays the library out as sections per folder by default; a scene's picker and a group's tab as one grid.
  const [view, setView] = useUrlChoiceIf<"folders" | "grid">(
    !embedded,
    "view",
    embedded ? "grid" : "folders",
    embedded ? ["folders"] : ["grid"],
  );
  const [size, setSize] = useTileSize();
  const [opened, setOpened] = useState<MediaItem | null>(null);
  const [adding, setAdding] = useState(false);
  const screens = Grid.useBreakpoint();
  const sidebar = !embedded && !lockedFolder && screens.lg !== false;

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (lockedFolder ?? shown) params.set("folder", (lockedFolder ?? shown)!);
    if (kind !== "all") params.set("kind", kind);
    if (query.trim()) params.set("q", query.trim());
    if (tagText) params.set("tags", tagText);
    try {
      const found = await api<MediaList>(`/media?${params.toString()}`);
      setData(found);
      setOpened((now) => (now ? (found.items.find((item) => item.id === now.id) ?? null) : null));
      // What is no longer listed (moved out of the filter, deleted by a teammate) stops being chosen.
      setSelected((ids) => ids.filter((id) => found.items.some((item) => item.id === id)));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [shown, lockedFolder, kind, query, tagText, message]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  async function remove(item: MediaItem) {
    try {
      await api(`/media/${item.id}`, "DELETE");
      setData((old) => ({ ...old, items: old.items.filter((row) => row.id !== item.id) }));
      setSelected((ids) => ids.filter((id) => id !== item.id));
      setOpened(null);
      await onChanged?.();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function dropOn(ids: number[], folder: string) {
    try {
      const result = await api<{ moved: number }>("/media/move", "POST", { ids, folder });
      message.success(`Đã chuyển ${result.moved} tư liệu vào “${folder}”`);
      setSelected([]);
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  const photos = data.items.filter((item) => item.kind === "photo").length;
  const clips = data.items.length - photos;
  const allChosen = data.items.length > 0 && data.items.every((item) => selected.includes(item.id));

  const folderChosen = !lockedFolder && shown && data.folders.some((row) => inFolder(row.folder, shown));
  const filtered = Boolean(shown || query.trim() || kind !== "all" || tagText);

  const upload = (
    <MediaUploadCard
      lockedFolder={lockedFolder}
      keyword={keyword}
      folders={data.folders}
      tags={data.tags}
      onAdded={() => {
        void load();
        void onChanged?.();
      }}
    />
  );

  const tileActions = (item: MediaItem) => [
    <Tooltip key="move" title="Chuyển thư mục">
      <Button
        type="text"
        size="small"
        icon={<FolderOutlined />}
        aria-label={`Chuyển thư mục ${item.name}`}
        onClick={() => setMoving({ ids: [item.id], current: item.folder })}
      />
    </Tooltip>,
    <Tooltip key="tags" title="Sửa thẻ">
      <Button
        type="text"
        size="small"
        icon={<TagsOutlined />}
        aria-label={`Sửa thẻ ${item.name}`}
        onClick={() => setTagEdit({ mode: "set", item })}
      />
    </Tooltip>,
    // Only whoever added it deletes it.
    ...(item.created_by_id !== me.id
      ? []
      : [
          <Popconfirm
            key="delete"
            title="Xoá khỏi kho?"
            description="Cảnh đã dùng tư liệu này vẫn giữ bản sao của nó."
            okText="Xoá"
            cancelText="Huỷ"
            onConfirm={() => remove(item)}
          >
            <Button type="text" danger size="small" icon={<DeleteOutlined />} aria-label={`Xoá ${item.name}`} />
          </Popconfirm>,
        ]),
  ];

  const toolbar = (
    <Card size="small" styles={{ body: { padding: 12 } }}>
      <Flex vertical gap={10}>
        <Flex gap={8} wrap align="center">
          <Input
            aria-label="Tìm tư liệu theo tên"
            prefix={<SearchOutlined />}
            allowClear
            placeholder="Tìm theo tên…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            style={{ flex: "1 1 200px", maxWidth: 280 }}
          />
          {!lockedFolder && !sidebar && (
            <FolderFilter
              aria-label="Lọc theo thư mục"
              folders={data.folders}
              value={shown}
              onChange={setShown}
              style={{ flex: "1 1 200px", maxWidth: 280 }}
            />
          )}
          <TagSelect
            aria-label="Lọc theo thẻ"
            placeholder="Mọi thẻ"
            tags={data.tags}
            value={tags}
            onChange={(next) => setTagText(next.join(","))}
            allowNew={false}
            maxTagCount="responsive"
            style={{ flex: "1 1 200px", maxWidth: 320 }}
          />
          <Segmented
            value={kind}
            onChange={(value) => setKind(value as typeof kind)}
            options={[
              { value: "all", label: "Tất cả" },
              { value: "photo", label: "Ảnh" },
              { value: "clip", label: "Clip" },
            ]}
          />
          <Flex gap={8} align="center" style={{ marginLeft: "auto" }}>
            <Segmented
              aria-label="Cách xếp"
              value={view}
              onChange={(value) => setView(value as typeof view)}
              options={[
                { value: "folders", label: "Theo thư mục" },
                { value: "grid", label: "Lưới" },
              ]}
            />
            <Segmented
              aria-label="Cỡ ảnh"
              value={size}
              onChange={(value) => setSize(value as TileSize)}
              options={[
                { value: "s", label: "S" },
                { value: "m", label: "M" },
                { value: "l", label: "L" },
              ]}
            />
          </Flex>
        </Flex>
        <Flex gap={8} wrap align="center" data-testid="media-selection" style={{ minHeight: 24 }}>
          {data.items.length > 0 && (
            <Button size="small" onClick={() => setSelected(allChosen ? [] : data.items.map((item) => item.id))}>
              {allChosen ? "Bỏ chọn tất cả" : "Chọn tất cả"}
            </Button>
          )}
          {selected.length > 0 ? (
            <>
              <Typography.Text>Đã chọn {selected.length} tư liệu</Typography.Text>
              <Button
                size="small"
                type="primary"
                icon={<FolderOutlined />}
                onClick={() => setMoving({ ids: selected })}
              >
                Chuyển thư mục
              </Button>
              <Button size="small" icon={<TagsOutlined />} onClick={() => setTagEdit({ mode: "add", ids: selected })}>
                Thêm thẻ
              </Button>
              <Button
                size="small"
                icon={<TagsOutlined />}
                onClick={() => setTagEdit({ mode: "remove", ids: selected })}
              >
                Gỡ thẻ
              </Button>
            </>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {data.items.length} tư liệu{photos && clips ? ` (${photos} ảnh, ${clips} clip)` : ""}
              {filtered && data.total > data.items.length ? ` trong ${data.total} của kho` : ""}
              {data.items.length >= 500 ? ", chỉ hiện 500 mới nhất" : ""}
            </Typography.Text>
          )}
          {folderChosen && (
            <span style={{ marginLeft: "auto" }}>
              <FolderActions
                folder={shown!}
                folders={data.folders}
                onRenamed={(to) => (to === shown ? void load() : setShown(to))}
                onCleared={() => setShown(null)}
              />
            </span>
          )}
        </Flex>
        <MediaGrid
          items={data.items}
          size={size}
          grouped={view === "folders"}
          empty={filtered ? "Không có tư liệu nào khớp bộ lọc" : undefined}
          selected={selected}
          onToggle={(id, chosen) =>
            setSelected((ids) => (chosen ? [...new Set([...ids, id])] : ids.filter((other) => other !== id)))
          }
          onOpen={setOpened}
          onDragStart={(item, event) => {
            const ids = selected.includes(item.id) ? selected : [item.id];
            event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(ids));
            event.dataTransfer.effectAllowed = "move";
          }}
          actions={tileActions}
        />
      </Flex>
    </Card>
  );

  return (
    <>
      {!embedded && (
        <PageHeader
          title="Kho tư liệu"
          description="Ảnh và clip của cả nhóm, dùng cho cảnh ở trang video hoặc nhờ Claude chọn."
          actions={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
              Thêm tư liệu
            </Button>
          }
        />
      )}
      <Flex gap={16} align="flex-start">
        {sidebar && (
          <Card
            size="small"
            styles={{ body: { padding: 8 } }}
            style={{
              width: 248,
              flex: "none",
              position: "sticky",
              top: 16,
              maxHeight: "calc(100vh - 32px)",
              overflow: "auto",
            }}
          >
            <FolderSidebar
              folders={data.folders}
              total={data.total}
              value={shown}
              onChange={setShown}
              onDropItems={dropOn}
            />
          </Card>
        )}
        <Flex vertical gap={16} style={{ flex: 1, minWidth: 0 }}>
          {embedded && showUpload && upload}
          {toolbar}
        </Flex>
      </Flex>
      {!embedded && (
        <Drawer
          open={adding}
          onClose={() => setAdding(false)}
          title="Thêm tư liệu"
          width={Math.min(760, typeof window === "undefined" ? 760 : window.innerWidth)}
        >
          {upload}
        </Drawer>
      )}
      <MediaDetailDrawer
        item={opened}
        canDelete={opened?.created_by_id === me.id}
        onClose={() => setOpened(null)}
        onMove={(item) => setMoving({ ids: [item.id], current: item.folder })}
        onTags={(item) => setTagEdit({ mode: "set", item })}
        onDelete={remove}
      />
      <TagEditModal
        edit={tagEdit}
        tags={data.tags}
        onClose={() => setTagEdit(null)}
        onSaved={() => {
          void load();
          void onChanged?.();
        }}
      />
      <MoveFolderModal
        ids={moving.ids}
        current={moving.current}
        folders={data.folders}
        onClose={() => setMoving({ ids: [] })}
        onMoved={() => {
          setSelected([]);
          void load();
        }}
      />
    </>
  );
}
