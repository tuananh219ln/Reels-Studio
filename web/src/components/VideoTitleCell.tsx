"use client";

import { Flex, Typography } from "antd";
import Link from "next/link";
import type { ReactNode } from "react";
import VideoThumbnail from "@/components/VideoThumbnail";

const THUMBNAIL = 36;
const GAP = 12;

/** A table's first cell for a video: its small thumbnail, its title linking to the video on up to two lines, and a
 * grey line under it. The link does not reach a row that opens or expands on click. The title and line are cut with
 * "…" at `maxWidth`, or sooner when the cell is narrower, so they never run over what is beside the cell. The cell as a
 * whole is capped in pixels too: a "…" line capped only in % counts at its full length when the table sizes its
 * columns, and would stretch the column far past the text. */
export default function VideoTitleCell({
  id,
  title,
  thumbnailUrl,
  sub,
  maxWidth = 520,
  editor,
}: {
  id: number;
  title: string;
  thumbnailUrl: string | null;
  sub?: ReactNode;
  maxWidth?: number;
  /** A VideoNameEditor to show in place of the title link. */
  editor?: ReactNode;
}) {
  return (
    <Flex align="center" gap={GAP} style={{ minWidth: 0, maxWidth: maxWidth + THUMBNAIL + GAP }}>
      <VideoThumbnail name={title} url={thumbnailUrl} width={THUMBNAIL} />
      <Flex vertical style={{ minWidth: 0, flex: 1 }}>
        {editor ?? (
          <Link
            prefetch={false}
            href={`/videos/${id}`}
            onClick={(event) => event.stopPropagation()}
            style={{ display: "block", maxWidth: "100%" }}
          >
            <Typography.Paragraph
              strong
              ellipsis={{ rows: 2, tooltip: title }}
              style={{ margin: 0, maxWidth: `min(${maxWidth}px, 100%)` }}
            >
              {title}
            </Typography.Paragraph>
          </Link>
        )}
        {sub && (
          <Typography.Text type="secondary" ellipsis style={{ maxWidth: `min(${maxWidth}px, 100%)`, fontSize: 12 }}>
            {sub}
          </Typography.Text>
        )}
      </Flex>
    </Flex>
  );
}
