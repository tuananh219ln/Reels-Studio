"use client";

import { Collapse, Flex, Typography } from "antd";
import type { VideoDetail } from "@/lib/api";
import { formatCompact } from "@/lib/competitorFormat";

/** "Clone từ <kênh>" on a video cloned from "Phân tích đối thủ", with the source video's sample comments folded
 * underneath (only to understand the viewers: they are never part of the script). */
export default function CompetitorSource({ source }: { source: NonNullable<VideoDetail["competitor_source"]> }) {
  const name = source.name || "video đối thủ";
  return (
    <Flex vertical gap={4} style={{ margin: "0 0 12px" }} data-testid="competitor-source">
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        Clone từ{" "}
        {source.url ? (
          <Typography.Link href={source.url} target="_blank" rel="noreferrer">
            {name}
          </Typography.Link>
        ) : (
          name
        )}
      </Typography.Text>
      {source.comments.length > 0 && (
        <Collapse
          size="small"
          items={[
            {
              key: "comments",
              label: `Bình luận mẫu (${source.comments.length})`,
              children: (
                <Flex vertical gap={6} style={{ maxHeight: 280, overflowY: "auto" }}>
                  {source.comments.map((comment, index) => (
                    <Flex key={index} gap={8} justify="space-between" align="baseline">
                      <Typography.Text style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{comment.text}</Typography.Text>
                      {comment.like_count !== null && (
                        <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
                          {formatCompact(comment.like_count)} thích
                        </Typography.Text>
                      )}
                    </Flex>
                  ))}
                </Flex>
              ),
            },
          ]}
        />
      )}
    </Flex>
  );
}
