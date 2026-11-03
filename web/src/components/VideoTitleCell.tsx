"use client";

import { Flex, Typography } from "antd";
import Link from "next/link";
import type { ReactNode } from "react";
import VideoThumbnail from "@/components/VideoThumbnail";

/** A table's first cell for a video: its small thumbnail, its title linking to the video, and a grey line under it.
 * The link does not reach a row that opens or expands on click. The title and line are cut with "…" at `maxWidth`, or
 * sooner when the cell is narrower, so they never run over what is beside the cell. */
export default function VideoTitleCell({
  id,
  title,
  thumbnailUrl,
  sub,
  maxWidth = 520,
}: {
  id: number;
  title: string;
  thumbnailUrl: string | null;
  sub?: ReactNode;
  maxWidth?: number;
}) {
  return (
    <Flex align="center" gap={12} style={{ minWidth: 0 }}>
      <VideoThumbnail name={title} url={thumbnailUrl} width={36} />
      <Flex vertical style={{ minWidth: 0, flex: 1 }}>
        <Link
          prefetch={false}
          href={`/videos/${id}`}
          onClick={(event) => event.stopPropagation()}
          style={{ display: "block", maxWidth: "100%" }}
        >
          <Typography.Text strong ellipsis={{ tooltip: title }} style={{ maxWidth: `min(${maxWidth}px, 100%)` }}>
            {title}
          </Typography.Text>
        </Link>
        {sub && (
          <Typography.Text type="secondary" ellipsis style={{ maxWidth: `min(${maxWidth}px, 100%)`, fontSize: 12 }}>
            {sub}
          </Typography.Text>
        )}
      </Flex>
    </Flex>
  );
}
