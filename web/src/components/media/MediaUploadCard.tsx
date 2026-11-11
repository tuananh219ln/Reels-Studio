"use client";

import { FolderOutlined, FolderAddOutlined, InboxOutlined, LinkOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Progress, Select, Tag, Typography, theme } from "antd";
import { useEffect, useRef, useState, type DragEvent } from "react";
import FolderSelect from "@/components/media/FolderSelect";
import MediaLinkSearch from "@/components/media/MediaLinkSearch";
import { api, errorMessage, upload, type AffiliateProduct, type MediaFolder, type MediaItem } from "@/lib/api";

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

/**
 * "Thêm tư liệu": a dropped or picked folder or files, uploaded one by one, and pasted links, into the folder chosen
 * from the library's folders (or a new one). `lockedFolder`: a topic group's "Tư liệu", where everything lands in the
 * group's folder (a dropped folder's own subfolders inside it) and `keyword` is what the searches look for.
 */
export default function MediaUploadCard({
  folders,
  lockedFolder,
  keyword = "",
  onAdded,
}: {
  folders: MediaFolder[];
  lockedFolder?: string;
  keyword?: string;
  onAdded: () => void;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const [products, setProducts] = useState<AffiliateProduct[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const target = lockedFolder ?? chosen ?? "";

  useEffect(() => {
    // A folder picker reads whole folders only through this non-standard attribute.
    folderInput.current?.setAttribute("webkitdirectory", "");
    if (lockedFolder !== undefined) return;
    api<AffiliateProduct[]>("/affiliate-products?status=approved")
      .then(setProducts)
      .catch(() => setProducts([]));
  }, [lockedFolder]);

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
    onAdded();
  }

  function picked(input: HTMLInputElement | null) {
    const files = Array.from(input?.files ?? []);
    if (input) input.value = "";
    // A picked folder gives each file its path inside it ("Nồi chiên/cảnh 1/a.mp4").
    void send(files.map((file) => ({ file, dir: file.webkitRelativePath.split("/").slice(0, -1).join("/") })));
  }

  return (
    <Card title={lockedFolder === undefined ? "Thêm tư liệu" : "Tải ảnh vào thư mục này"} size="small">
      <Flex vertical gap={12}>
        {lockedFolder === undefined ? (
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
                setChosen(name ? name.slice(0, 80).replaceAll("/", "-") : null);
              }}
              style={{ flex: "1 1 280px" }}
            />
            <FolderSelect
              aria-label="Thư mục"
              folders={folders}
              value={chosen}
              onChange={setChosen}
              placeholder="Thư mục (không bắt buộc), gõ để tạo mới…"
              style={{ flex: "1 1 220px" }}
            />
          </Flex>
        ) : (
          <Typography.Text>
            Vào thư mục{" "}
            <Tag icon={<FolderOutlined />} style={{ marginInlineEnd: 0 }}>
              {lockedFolder}
            </Tag>
          </Typography.Text>
        )}
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
            <Typography.Text type="secondary">Ảnh tối đa 15 MB; video tối đa 50 MB, giữ 1 phút đầu.</Typography.Text>
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
        <MediaLinkSearch keyword={product?.name ?? keyword} folder={target} onAdded={onAdded} />
      </Flex>
    </Card>
  );
}
