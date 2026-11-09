"use client";

import { useMe } from "@/components/MeContext";
import { DeleteOutlined, FolderAddOutlined, InboxOutlined, LinkOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Progress, Segmented, Select, Typography, theme } from "antd";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import MediaGrid from "@/components/media/MediaGrid";
import MediaLinkSearch from "@/components/media/MediaLinkSearch";
import PageHeader from "@/components/PageHeader";
import { api, errorMessage, upload, type AffiliateProduct, type MediaItem, type MediaList } from "@/lib/api";

const MAX_PHOTO_BYTES = 15 * 1024 * 1024;
const MAX_CLIP_BYTES = 50 * 1024 * 1024;
const MEDIA_FILE = /\.(jpe?g|png|webp|mp4|mov|webm)$/i;

type Pending = { file: File; dir: string };

/** Every file of a dropped folder (or of dropped files), with the folder path it sat in. */
async function droppedFiles(event: DragEvent): Promise<Pending[]> {
  const found: Pending[] = [];
  const walk = async (entry: FileSystemEntry, dir: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      found.push({ file, dir });
      return;
    }
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    const path = dir ? `${dir}/${entry.name}` : entry.name;
    // readEntries answers in batches: read until it returns nothing.
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      for (const child of batch) await walk(child, path);
    }
  };
  const entries = Array.from(event.dataTransfer.items)
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry !== null);
  for (const entry of entries) await walk(entry, "");
  return found;
}

export default function MediaPage() {
  const { message } = App.useApp();
  const { me } = useMe();
  const { token } = theme.useToken();
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const [data, setData] = useState<MediaList>({ items: [], folders: [] });
  const [products, setProducts] = useState<AffiliateProduct[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [target, setTarget] = useState("");
  const [shown, setShown] = useState<string | null>(null);
  const [kind, setKind] = useState<"all" | "photo" | "clip">("all");
  const [query, setQuery] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (shown) params.set("folder", shown);
    if (kind !== "all") params.set("kind", kind);
    if (query.trim()) params.set("q", query.trim());
    try {
      setData(await api<MediaList>(`/media?${params.toString()}`));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [shown, kind, query, message]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    api<AffiliateProduct[]>("/affiliate-products?status=approved")
      .then(setProducts)
      .catch(() => setProducts([]));
    // A folder picker reads whole folders only through this non-standard attribute.
    folderInput.current?.setAttribute("webkitdirectory", "");
  }, []);

  const product = products.find((row) => row.id === productId) ?? null;

  async function send(pending: Pending[]) {
    const usable = pending.filter(({ file }) => MEDIA_FILE.test(file.name));
    const skipped = pending.length - usable.length;
    if (!usable.length) {
      message.warning("Không có ảnh (jpg, png, webp) hay video (mp4, mov, webm) nào");
      return;
    }
    setProgress({ done: 0, total: usable.length });
    let failed = 0;
    // One file per request, like every upload: Cloudflare caps a request at 100 MB.
    for (const [index, { file, dir }] of usable.entries()) {
      const tooBig = /\.(mp4|mov|webm)$/i.test(file.name) ? file.size > MAX_CLIP_BYTES : file.size > MAX_PHOTO_BYTES;
      if (tooBig) {
        failed += 1;
        message.error(`“${file.name}” quá lớn (ảnh tối đa 15 MB, video 50 MB)`);
      } else {
        try {
          await upload<MediaItem>("/media", file, { folder: [target, dir].filter(Boolean).join("/") });
        } catch (err) {
          failed += 1;
          message.error(`“${file.name}”: ${errorMessage(err)}`);
        }
      }
      setProgress({ done: index + 1, total: usable.length });
    }
    setProgress(null);
    const added = usable.length - failed;
    if (added) message.success(`Đã thêm ${added} tư liệu${skipped ? `, bỏ qua ${skipped} file khác loại` : ""}`);
    await load();
  }

  function picked(input: HTMLInputElement | null) {
    const files = Array.from(input?.files ?? []);
    if (input) input.value = "";
    // A picked folder gives each file its path inside it ("Nồi chiên/cảnh 1/a.mp4").
    void send(files.map((file) => ({ file, dir: file.webkitRelativePath.split("/").slice(0, -1).join("/") })));
  }

  async function remove(item: MediaItem) {
    try {
      await api(`/media/${item.id}`, "DELETE");
      setData((old) => ({ ...old, items: old.items.filter((row) => row.id !== item.id) }));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Kho tư liệu"
        description="Ảnh và clip của cả nhóm: kéo cả thư mục vào, hoặc tìm trên Google, TikTok rồi dán link. Dùng cho cảnh ở trang video hoặc nhờ Claude chọn."
      />
      <Flex vertical gap={16}>
        <Card title="Thêm tư liệu" size="small">
          <Flex vertical gap={12}>
            <Flex gap={8} wrap align="center">
              <Select
                allowClear
                showSearch
                placeholder="Sản phẩm đang làm (để tìm và đặt thư mục)"
                optionFilterProp="label"
                value={productId ?? undefined}
                options={products.map((row) => ({ value: row.id, label: row.name }))}
                onChange={(value: number | undefined) => {
                  setProductId(value ?? null);
                  const name = products.find((row) => row.id === value)?.name ?? "";
                  setTarget(name.slice(0, 80).replaceAll("/", "-"));
                }}
                style={{ flex: "1 1 280px" }}
              />
              <Input
                aria-label="Thư mục"
                prefix={<FolderAddOutlined />}
                placeholder="Thư mục (không bắt buộc)"
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                style={{ flex: "1 1 220px" }}
              />
            </Flex>
            <div
              data-testid="media-drop"
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={async (event) => {
                event.preventDefault();
                setDragging(false);
                void send(await droppedFiles(event));
              }}
              style={{
                border: `1px dashed ${dragging ? token.colorPrimary : token.colorBorder}`,
                borderRadius: 8,
                padding: 20,
                textAlign: "center",
                background: dragging ? token.colorPrimaryBg : undefined,
              }}
            >
              <Flex vertical gap={8} align="center">
                <InboxOutlined style={{ fontSize: 32, color: token.colorPrimary }} />
                <Typography.Text>Kéo cả thư mục hoặc nhiều file ảnh, video vào đây</Typography.Text>
                <Flex gap={8} wrap justify="center">
                  <Button icon={<FolderAddOutlined />} onClick={() => folderInput.current?.click()}>
                    Chọn thư mục
                  </Button>
                  <Button icon={<UploadOutlined />} onClick={() => filesInput.current?.click()}>
                    Chọn file
                  </Button>
                </Flex>
                <Typography.Text type="secondary">
                  Ảnh tối đa 15 MB; video tối đa 50 MB, giữ 1 phút đầu.
                </Typography.Text>
              </Flex>
              <input ref={folderInput} type="file" multiple hidden onChange={(e) => picked(e.currentTarget)} />
              <input
                ref={filesInput}
                type="file"
                multiple
                hidden
                accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm"
                onChange={(e) => picked(e.currentTarget)}
              />
            </div>
            {progress && <Progress percent={Math.round((progress.done / progress.total) * 100)} />}
            <Typography.Text strong>
              <LinkOutlined /> Tìm trên Google, TikTok rồi dán link
            </Typography.Text>
            <MediaLinkSearch keyword={product?.name ?? ""} folder={target} onAdded={() => void load()} />
          </Flex>
        </Card>
        <Card size="small">
          <Flex vertical gap={12}>
            <Flex gap={8} wrap align="center">
              <Select
                allowClear
                placeholder="Mọi thư mục"
                value={shown ?? undefined}
                onChange={(value: string | undefined) => setShown(value ?? null)}
                options={data.folders.map(({ folder, count }) => ({ value: folder, label: `${folder} (${count})` }))}
                style={{ flex: "1 1 220px" }}
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
              <Input.Search
                allowClear
                placeholder="Tìm theo tên"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                style={{ flex: "1 1 200px" }}
              />
            </Flex>
            <MediaGrid
              items={data.items}
              actions={(item) =>
                // Only whoever added it deletes it.
                item.created_by_id !== me.id
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
                    ]
              }
            />
          </Flex>
        </Card>
      </Flex>
    </>
  );
}
