"use client";

import EmptyState from "@/components/EmptyState";
import type { MediaItem } from "@/lib/api";
import { isSmall, shapeOf, specLine, formatClock } from "@/lib/mediaSpecs";
import { CaretDownOutlined, CaretRightOutlined, VideoCameraFilled } from "@ant-design/icons";
import { Checkbox, Flex, Tag, Typography, theme } from "antd";
import { useState, type ReactNode } from "react";

/** How big the tiles are: the member's choice on the page ("Cỡ ảnh"). */
export type TileSize = "s" | "m" | "l";
const MIN_WIDTH: Record<TileSize, number> = { s: 104, m: 136, l: 184 };

const NO_FOLDER = "Không thư mục";

/** The items as `[folder, items]` sections: folders by name as people read them, "Không thư mục" last. */
export function groupByFolder(items: MediaItem[]): [string, MediaItem[]][] {
  const groups = new Map<string, MediaItem[]>();
  for (const item of items) groups.set(item.folder, [...(groups.get(item.folder) ?? []), item]);
  return [...groups].sort(([a], [b]) =>
    a === "" ? 1 : b === "" ? -1 : a.localeCompare(b, "vi", { sensitivity: "base" }) || a.localeCompare(b),
  );
}

const STYLE = `
.mtile .mcheck, .mtile .mactions { opacity: 0; transition: opacity .12s; }
.mtile:hover .mcheck, .mtile:hover .mactions, .mtile:focus-within .mcheck, .mtile:focus-within .mactions,
.mgrid[data-selecting="true"] .mcheck, .mtile[data-chosen="true"] .mcheck { opacity: 1; }
@media (hover: none) { .mtile .mcheck, .mtile .mactions { opacity: 1; } }
`;

/**
 * The library's photos and clips as small tiles (the picture, its name and its numbers under it), each with the
 * actions its page gives it. `onOpen` makes a tile open its details; `onToggle` gives each a box to choose it for an
 * action on several at once; `onDragStart` lets a tile be dropped on a folder; `grouped` lays the tiles out in one
 * collapsible section per folder. Without `onOpen`, `actions` sit in a row under the tile (the scene's picker).
 */
export default function MediaGrid({
  items,
  actions,
  empty = "Kho chưa có tư liệu nào",
  selected,
  onToggle,
  onOpen,
  onDragStart,
  size = "m",
  grouped = false,
}: {
  items: MediaItem[];
  actions: (item: MediaItem) => ReactNode[];
  empty?: ReactNode;
  selected?: number[];
  onToggle?: (id: number, chosen: boolean) => void;
  onOpen?: (item: MediaItem) => void;
  onDragStart?: (item: MediaItem, event: React.DragEvent) => void;
  size?: TileSize;
  grouped?: boolean;
}) {
  const [closed, setClosed] = useState<string[]>([]);
  const { token } = theme.useToken();
  if (!items.length) return <EmptyState description={empty} />;

  const tiles = (list: MediaItem[]) => (
    <div
      className="mgrid"
      data-selecting={Boolean(selected?.length)}
      style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${MIN_WIDTH[size]}px, 1fr))`, gap: 10 }}
    >
      {list.map((item) => (
        <Tile
          key={item.id}
          item={item}
          size={size}
          chosen={selected?.includes(item.id) ?? false}
          onToggle={onToggle}
          onOpen={onOpen}
          onDragStart={onDragStart}
          actions={actions(item)}
          overlayActions={Boolean(onOpen)}
        />
      ))}
    </div>
  );

  const sections = grouped ? groupByFolder(items) : null;
  return (
    <>
      <style>{STYLE}</style>
      {sections ? (
        <Flex vertical gap={16}>
          {sections.map(([folder, list]) => {
            const open = !closed.includes(folder);
            const allChosen = list.every((item) => selected?.includes(item.id));
            return (
              <section key={folder} data-testid="media-group" aria-label={folder || NO_FOLDER}>
                <Flex align="center" gap={8} style={{ marginBottom: 8 }}>
                  <Typography.Link
                    type="secondary"
                    aria-label={`${open ? "Thu gọn" : "Mở"} ${folder || NO_FOLDER}`}
                    onClick={() =>
                      setClosed((now) => (open ? [...now, folder] : now.filter((path) => path !== folder)))
                    }
                    style={{ color: token.colorTextSecondary }}
                  >
                    {open ? <CaretDownOutlined /> : <CaretRightOutlined />}
                  </Typography.Link>
                  <Typography.Text strong ellipsis style={{ minWidth: 0 }}>
                    {folder || NO_FOLDER}
                  </Typography.Text>
                  <Typography.Text type="secondary">{list.length}</Typography.Text>
                  {onToggle && (
                    <Checkbox
                      aria-label={`Chọn cả ${folder || NO_FOLDER}`}
                      checked={allChosen}
                      onChange={(event) => list.forEach((item) => onToggle(item.id, event.target.checked))}
                    />
                  )}
                </Flex>
                {open && tiles(list)}
              </section>
            );
          })}
        </Flex>
      ) : (
        tiles(items)
      )}
    </>
  );
}

function Tile({
  item,
  size,
  chosen,
  onToggle,
  onOpen,
  onDragStart,
  actions,
  overlayActions,
}: {
  item: MediaItem;
  size: TileSize;
  chosen: boolean;
  onToggle?: (id: number, chosen: boolean) => void;
  onOpen?: (item: MediaItem) => void;
  onDragStart?: (item: MediaItem, event: React.DragEvent) => void;
  actions: ReactNode[];
  overlayActions: boolean;
}) {
  const { token } = theme.useToken();
  const specs = specLine(item);
  const shape = shapeOf(item);
  const warn = isSmall(item);
  return (
    <div
      className="mtile"
      data-testid="media-item"
      data-chosen={chosen}
      draggable={Boolean(onDragStart)}
      onDragStart={(event) => onDragStart?.(item, event)}
      style={{ minWidth: 0 }}
    >
      <div
        style={{
          position: "relative",
          aspectRatio: "9 / 16",
          background: token.colorFillTertiary,
          borderRadius: token.borderRadius,
          overflow: "hidden",
          outline: chosen ? `2px solid ${token.colorPrimary}` : undefined,
          outlineOffset: -2,
          cursor: onOpen ? "pointer" : undefined,
        }}
        onClick={onOpen ? () => onOpen(item) : undefined}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- a private api image, not for next/image */}
        <img
          src={item.thumb_url}
          alt={item.name}
          loading="lazy"
          draggable={false}
          style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        />
        {onToggle && (
          <Checkbox
            className="mcheck"
            aria-label={`Chọn ${item.name}`}
            checked={chosen}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => onToggle(item.id, event.target.checked)}
            style={{
              position: "absolute",
              left: 4,
              top: 4,
              padding: 5,
              borderRadius: token.borderRadiusSM,
              background: token.colorBgContainer,
            }}
          />
        )}
        {overlayActions && (
          <Flex
            className="mactions"
            gap={0}
            onClick={(event) => event.stopPropagation()}
            style={{
              position: "absolute",
              right: 4,
              top: 4,
              borderRadius: token.borderRadiusSM,
              background: token.colorBgContainer,
            }}
          >
            {actions}
          </Flex>
        )}
        <Flex gap={4} style={{ position: "absolute", left: 4, bottom: 4, right: 4 }} wrap>
          {item.kind === "clip" && (
            <Tag
              icon={<VideoCameraFilled />}
              style={{ margin: 0, paddingInline: 5, lineHeight: "18px", fontSize: 11 }}
              bordered={false}
              color="black"
            >
              {item.seconds === null ? "Clip" : formatClock(item.seconds)}
            </Tag>
          )}
          {warn && (
            <Tag color="warning" style={{ margin: 0, paddingInline: 5, lineHeight: "18px", fontSize: 11 }}>
              Nhỏ
            </Tag>
          )}
          {shape && shape !== "tall" && (
            <Tag style={{ margin: 0, paddingInline: 5, lineHeight: "18px", fontSize: 11 }}>
              {shape === "wide" ? "Ngang" : "Vuông"}
            </Tag>
          )}
        </Flex>
      </div>
      <Flex vertical gap={1} style={{ minWidth: 0, padding: "4px 2px 0" }}>
        <Typography.Text ellipsis={{ tooltip: item.name }} style={{ fontSize: 12, fontWeight: 500 }}>
          {item.name}
        </Typography.Text>
        {size !== "s" && specs && (
          <Typography.Text type="secondary" ellipsis style={{ fontSize: 11 }}>
            {specs}
          </Typography.Text>
        )}
        {item.tags.length > 0 && (
          <Typography.Text
            type="secondary"
            ellipsis
            data-testid="media-tags"
            title={item.tags.join(", ")}
            style={{ fontSize: 11 }}
          >
            {item.tags.join(" · ")}
          </Typography.Text>
        )}
        {!overlayActions && actions.length > 0 && <Flex gap={0}>{actions}</Flex>}
      </Flex>
    </div>
  );
}
