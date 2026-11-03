"use client";

import { Flex, Typography } from "antd";
import Link from "next/link";
import type { ReactNode } from "react";
import VideoThumbnail from "@/components/VideoThumbnail";

/** A table's first cell for a video: its small thumbnail, its title linking to the video, and a grey line under it.
 * The link does not reach a row that opens or expands on click. */
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
    <Flex align="center" gap={12}>
      <VideoThumbnail name={title} url={thumbnailUrl} width={36} />
      <Flex vertical style={{ minWidth: 0 }}>
        <Link prefetch={false} href={`/videos/${id}`} onClick={(event) => event.stopPropagation()}>
          <Typography.Text strong ellipsis style={{ maxWidth }}>
            {title}
          </Typography.Text>
        </Link>
        {sub && (
          <Typography.Text type="secondary" ellipsis style={{ maxWidth, fontSize: 12 }}>
            {sub}
          </Typography.Text>
        )}
      </Flex>
    </Flex>
  );
}
