"use client";

import type { MediaItem } from "@/lib/api";
import { formatDateTime } from "@/lib/api";
import { formatBytes, formatClock, isSmall, shapeOf, SMALL_SIDE } from "@/lib/mediaSpecs";
import { DeleteOutlined, DownloadOutlined, FolderOutlined, TagsOutlined } from "@ant-design/icons";
import { Alert, Button, Descriptions, Drawer, Flex, Popconfirm, Tag, Typography } from "antd";
import type { ReactNode } from "react";

const SHAPE_TEXT = {
  tall: "Dọc, vừa khung 9:16",
  square: "Gần vuông: hai bên bị cắt khi lấp khung 9:16",
  wide: "Ngang: hai bên bị cắt nhiều khi lấp khung 9:16",
} as const;

/**
 * An item's details ("Thông số"): the picture or clip large, its numbers, where it came from, and the same actions
 * as its tile. Null `item`: closed.
 */
export default function MediaDetailDrawer({
  item,
  canDelete,
  onClose,
  onMove,
  onTags,
  onDelete,
}: {
  item: MediaItem | null;
  canDelete: boolean;
  onClose: () => void;
  onMove: (item: MediaItem) => void;
  onTags: (item: MediaItem) => void;
  onDelete: (item: MediaItem) => void;
}) {
  const shape = item ? shapeOf(item) : null;
  const rows: { key: string; label: string; children: ReactNode }[] = item
    ? [
        { key: "kind", label: "Loại", children: item.kind === "clip" ? "Clip" : "Ảnh" },
        ...(item.kind === "photo" && item.width && item.height
          ? [{ key: "px", label: "Kích thước", children: `${item.width} × ${item.height} px` }]
          : []),
        ...(item.kind === "clip" && item.seconds !== null
          ? [{ key: "len", label: "Thời lượng", children: `${formatClock(item.seconds)} (${item.seconds} giây)` }]
          : []),
        ...(item.size_bytes !== null
          ? [{ key: "size", label: "Dung lượng", children: formatBytes(item.size_bytes) }]
          : []),
        { key: "folder", label: "Thư mục", children: item.folder || "Không thư mục" },
        {
          key: "tags",
          label: "Thẻ",
          children: item.tags.length ? (
            <Flex wrap gap={4}>
              {item.tags.map((tag) => (
                <Tag key={tag} style={{ margin: 0 }}>
                  {tag}
                </Tag>
              ))}
            </Flex>
          ) : (
            "Chưa có thẻ"
          ),
        },
        { key: "by", label: "Người thêm", children: item.created_by },
        { key: "at", label: "Ngày thêm", children: formatDateTime(item.created_at) },
        ...(item.source_url
          ? [
              {
                key: "src",
                label: "Nguồn",
                children: (
                  <Typography.Link href={item.source_url} target="_blank" rel="noreferrer" ellipsis>
                    {item.source_url}
                  </Typography.Link>
                ),
              },
            ]
          : []),
      ]
    : [];
  return (
    <Drawer open={item !== null} onClose={onClose} width={420} title={item?.name ?? ""} destroyOnHidden>
      {item && (
        <Flex vertical gap={16}>
          <div style={{ background: "#000", borderRadius: 8, overflow: "hidden", textAlign: "center" }}>
            {item.kind === "clip" ? (
              <video
                src={item.file_url}
                poster={item.thumb_url}
                controls
                preload="none"
                style={{ maxWidth: "100%", maxHeight: "60vh" }}
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element -- a private api image, not for next/image
              <img src={item.file_url} alt={item.name} style={{ maxWidth: "100%", maxHeight: "60vh" }} />
            )}
          </div>
          {shape && (
            <Alert
              type={shape === "tall" && !isSmall(item) ? "success" : "warning"}
              showIcon
              message={
                isSmall(item)
                  ? `Ảnh nhỏ (cạnh ngắn dưới ${SMALL_SIDE} px), có thể bị mờ trong video`
                  : SHAPE_TEXT[shape]
              }
            />
          )}
          <Descriptions column={1} size="small" colon={false} items={rows} labelStyle={{ width: 96 }} />
          <Flex gap={8} wrap>
            <Button icon={<FolderOutlined />} onClick={() => onMove(item)}>
              Chuyển thư mục
            </Button>
            <Button icon={<TagsOutlined />} onClick={() => onTags(item)}>
              Sửa thẻ
            </Button>
            <Button icon={<DownloadOutlined />} href={item.file_url} download={item.name}>
              Tải về
            </Button>
            {canDelete && (
              <Popconfirm
                title="Xoá khỏi kho?"
                description="Cảnh đã dùng tư liệu này vẫn giữ bản sao của nó."
                okText="Xoá"
                cancelText="Huỷ"
                onConfirm={() => onDelete(item)}
              >
                <Button danger icon={<DeleteOutlined />}>
                  Xoá
                </Button>
              </Popconfirm>
            )}
          </Flex>
        </Flex>
      )}
    </Drawer>
  );
}
