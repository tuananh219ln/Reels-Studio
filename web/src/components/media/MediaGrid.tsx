"use client";

import EmptyState from "@/components/EmptyState";
import { VideoCameraOutlined } from "@ant-design/icons";
import { Card, Flex, Tag, Typography, theme } from "antd";
import type { ReactNode } from "react";
import type { MediaItem } from "@/lib/api";
import { formatDecimal } from "@/lib/api";

/** The library's photos and clips as tall cards, each with the actions its page gives it. */
export default function MediaGrid({
  items,
  actions,
  empty = "Kho chưa có tư liệu nào",
}: {
  items: MediaItem[];
  actions: (item: MediaItem) => ReactNode[];
  empty?: string;
}) {
  const { token } = theme.useToken();
  if (!items.length) {
    return <EmptyState description={empty} />;
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12 }}>
      {items.map((item) => (
        <Card
          key={item.id}
          size="small"
          data-testid="media-item"
          styles={{ body: { padding: 8 } }}
          cover={
            <div
              style={{
                position: "relative",
                aspectRatio: "9 / 16",
                background: token.colorFillTertiary,
                overflow: "hidden",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- a private api image, not for next/image */}
              <img
                src={item.thumb_url}
                alt={item.name}
                loading="lazy"
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
              {item.kind === "clip" && (
                <Tag icon={<VideoCameraOutlined />} style={{ position: "absolute", left: 6, bottom: 6, margin: 0 }}>
                  {item.seconds === null || item.seconds === undefined ? "" : formatDecimal(item.seconds)} giây
                </Tag>
              )}
            </div>
          }
          actions={actions(item)}
        >
          <Flex vertical gap={2} style={{ minWidth: 0 }}>
            <Typography.Text ellipsis={{ tooltip: item.name }} strong>
              {item.name}
            </Typography.Text>
            {item.folder && (
              <Typography.Text type="secondary" ellipsis={{ tooltip: item.folder }} style={{ fontSize: 12 }}>
                {item.folder}
              </Typography.Text>
            )}
          </Flex>
        </Card>
      ))}
    </div>
  );
}
