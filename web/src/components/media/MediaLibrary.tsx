"use client";

import { useMe } from "@/components/MeContext";
import FolderActions from "@/components/media/FolderActions";
import { FolderFilter } from "@/components/media/FolderSelect";
import MediaGrid from "@/components/media/MediaGrid";
import MediaUploadCard from "@/components/media/MediaUploadCard";
import MoveFolderModal from "@/components/media/MoveFolderModal";
import TagEditModal, { type TagEdit } from "@/components/media/TagEditModal";
import TagSelect from "@/components/media/TagSelect";
import PageHeader from "@/components/PageHeader";
import { api, errorMessage, type MediaItem, type MediaList } from "@/lib/api";
import { inFolder } from "@/lib/folderTree";
import { useUrlChoiceIf } from "@/lib/urlState";
import { DeleteOutlined, FolderOutlined, SearchOutlined, TagsOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Segmented, Tooltip, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

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
  const [data, setData] = useState<MediaList>({ items: [], folders: [], tags: [] });
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

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (lockedFolder ?? shown) params.set("folder", (lockedFolder ?? shown)!);
    if (kind !== "all") params.set("kind", kind);
    if (query.trim()) params.set("q", query.trim());
    if (tagText) params.set("tags", tagText);
    try {
      const found = await api<MediaList>(`/media?${params.toString()}`);
      setData(found);
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
      await onChanged?.();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  const allChosen = data.items.length > 0 && data.items.every((item) => selected.includes(item.id));

  return (
    <>
      {!embedded && (
        <PageHeader
          title="Kho tư liệu"
          description="Ảnh và clip của cả nhóm: kéo cả thư mục vào, hoặc tìm trên Google, TikTok rồi dán link. Dùng cho cảnh ở trang video hoặc nhờ Claude chọn."
        />
      )}
      <Flex vertical gap={16}>
        {showUpload && (
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
        )}

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
              {!lockedFolder && (
                <FolderFilter
                  aria-label="Lọc theo thư mục"
                  folders={data.folders}
                  value={shown}
                  onChange={setShown}
                  style={{ flex: "1 1 220px", maxWidth: 320 }}
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
                style={{ flex: "1 1 220px", maxWidth: 360 }}
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
              {!lockedFolder && shown && data.folders.some((row) => inFolder(row.folder, shown)) && (
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
                    <Button
                      size="small"
                      icon={<TagsOutlined />}
                      onClick={() => setTagEdit({ mode: "add", ids: selected })}
                    >
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
                )}
              </Flex>
            )}
            <MediaGrid
              items={data.items}
              empty={
                shown || query.trim() || kind !== "all" || tagText ? "Không có tư liệu nào khớp bộ lọc" : undefined
              }
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
