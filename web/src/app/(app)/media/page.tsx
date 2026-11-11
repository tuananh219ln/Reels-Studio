"use client";

import { useMe } from "@/components/MeContext";
import { DeleteOutlined, FolderOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Segmented, Tooltip, Typography } from "antd";
import { Suspense, useCallback, useEffect, useState } from "react";
import FilterSelect from "@/components/FilterSelect";
import FolderActions from "@/components/media/FolderActions";
import { folderLabel } from "@/components/media/FolderSelect";
import MediaGrid from "@/components/media/MediaGrid";
import MediaUploadCard from "@/components/media/MediaUploadCard";
import MoveFolderModal from "@/components/media/MoveFolderModal";
import PageHeader from "@/components/PageHeader";
import { api, errorMessage, type MediaItem, type MediaList } from "@/lib/api";
import { useUrlChoice } from "@/lib/urlState";

export default function MediaPage() {
  // The folder, kind and search are in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Media />
    </Suspense>
  );
}

function Media() {
  const { message } = App.useApp();
  const { me } = useMe();
  const [data, setData] = useState<MediaList>({ items: [], folders: [] });
  const [shown, setShown] = useUrlChoice<string | null>("folder", null);
  const [kind, setKind] = useUrlChoice<"all" | "photo" | "clip">("kind", "all", ["photo", "clip"]);
  const [query, setQuery] = useUrlChoice<string>("q", "");
  // Items chosen for "Chuyển thư mục" on several at once, and what the dialog moves (one item or the chosen ones).
  const [selected, setSelected] = useState<number[]>([]);
  const [moving, setMoving] = useState<{ ids: number[]; current?: string }>({ ids: [] });

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (shown) params.set("folder", shown);
    if (kind !== "all") params.set("kind", kind);
    if (query.trim()) params.set("q", query.trim());
    try {
      const found = await api<MediaList>(`/media?${params.toString()}`);
      setData(found);
      // What is no longer listed (moved out of the filter, deleted by a teammate) stops being chosen.
      setSelected((ids) => ids.filter((id) => found.items.some((item) => item.id === id)));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [shown, kind, query, message]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  async function remove(item: MediaItem) {
    try {
      await api(`/media/${item.id}`, "DELETE");
      setData((old) => ({ ...old, items: old.items.filter((row) => row.id !== item.id) }));
      setSelected((ids) => ids.filter((id) => id !== item.id));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  const allChosen = data.items.length > 0 && data.items.every((item) => selected.includes(item.id));

  return (
    <>
      <PageHeader
        title="Kho tư liệu"
        description="Ảnh và clip của cả nhóm: kéo cả thư mục vào, hoặc tìm trên Google, TikTok rồi dán link. Dùng cho cảnh ở trang video hoặc nhờ Claude chọn."
      />
      <Flex vertical gap={16}>
        <MediaUploadCard folders={data.folders} onAdded={() => void load()} />
        <Card size="small">
          <Flex vertical gap={12}>
            <Flex gap={8} wrap align="center">
              <Input
                aria-label="Tìm tư liệu theo tên"
                prefix={<SearchOutlined />}
                allowClear
                placeholder="Tìm theo tên…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                style={{ flex: "1 1 220px", maxWidth: 320 }}
              />
              <FilterSelect<string>
                aria-label="Lọc theo thư mục"
                placeholder="Mọi thư mục"
                value={shown}
                onChange={(value) => setShown(value ?? null)}
                options={data.folders.map((row) => ({ value: row.folder, label: folderLabel(row) }))}
                style={{ flex: "1 1 220px", maxWidth: 320 }}
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
              {/* Once the folders are read, so the dialogs count what the folder holds. */}
              {shown && data.folders.some((row) => row.folder === shown) && (
                <FolderActions
                  folder={shown}
                  folders={data.folders}
                  onRenamed={(to) => (to === shown ? void load() : setShown(to))}
                  onCleared={() => setShown(null)}
                />
              )}
            </Flex>
            {data.items.length > 0 && (
              <Flex gap={8} wrap align="center" data-testid="media-selection">
                <Button size="small" onClick={() => setSelected(allChosen ? [] : data.items.map((item) => item.id))}>
                  {allChosen ? "Bỏ chọn tất cả" : "Chọn tất cả"}
                </Button>
                {selected.length > 0 && (
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
                  </>
                )}
              </Flex>
            )}
            <MediaGrid
              items={data.items}
              empty={shown || query.trim() || kind !== "all" ? "Không có tư liệu nào khớp bộ lọc" : undefined}
              selected={selected}
              onToggle={(id, chosen) =>
                setSelected((ids) => (chosen ? [...ids, id] : ids.filter((other) => other !== id)))
              }
              actions={(item) => [
                <Tooltip key="move" title="Chuyển thư mục">
                  <Button
                    type="text"
                    size="small"
                    icon={<FolderOutlined />}
                    aria-label={`Chuyển thư mục ${item.name}`}
                    onClick={() => setMoving({ ids: [item.id], current: item.folder })}
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
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          aria-label={`Xoá ${item.name}`}
                        />
                      </Popconfirm>,
                    ]),
              ]}
            />
          </Flex>
        </Card>
      </Flex>
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
