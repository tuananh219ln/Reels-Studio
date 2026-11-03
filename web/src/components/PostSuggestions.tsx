"use client";

import { SendOutlined } from "@ant-design/icons";
import { Button, Card, Flex, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, formatDateTime, type PostRow, type VideoRow } from "@/lib/api";
import VideoTitleCell from "@/components/VideoTitleCell";

/** How many videos show before "Xem thêm". */
const SHORT = 5;

const isActive = (post: PostRow) => post.status === "scheduled" || post.status === "published";

/** A rendered MP4 that matches the video as it is now, and no job running on it. */
const postable = (video: VideoRow) => video.status === "done" && !video.mp4_outdated;

/** The link that opens a video's "Đăng" dialog, with the Page picked when one is given. */
export function publishHref(videoId: number, fanpageId?: number): string {
  return `/videos/${videoId}?publish=${fanpageId ?? ""}`;
}

/** Rendered videos with no live or scheduled post, oldest first: they were made and are waiting. */
export function readyToPost(videos: VideoRow[], posts: PostRow[]): VideoRow[] {
  const live = new Set(posts.filter(isActive).map((post) => post.video_id));
  return videos
    .filter((video) => postable(video) && !live.has(video.id))
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/** The list above "Bài đăng" of what is made and waiting to go out; each opens the video's "Đăng" dialog. `posts`
 * (every post) changes when the list is reloaded, so the videos are read again with it. A failure leaves the list
 * out: the table below still works. Posting the same MP4 to another Page is not suggested: Facebook shows a copy less
 * and can stop paying a Page that repeats content (docs/specs/multi-platform/plan.md). */
export default function PostSuggestions({ posts }: { posts: PostRow[] | null }) {
  const [videos, setVideos] = useState<VideoRow[] | null>(null);

  useEffect(() => {
    api<VideoRow[]>("/videos").then(setVideos, () => setVideos(null));
  }, [posts]);

  if (!posts || !videos) return null;
  const ready = readyToPost(videos, posts);

  return (
    <div style={{ marginBottom: 16 }}>
      <SuggestionCard
        testId="ready-to-post"
        title="Sẵn sàng đăng"
        help="Video đã render xong nhưng chưa có bài nào đang đăng hoặc hẹn lịch, video cũ nhất trước."
        empty="Không có video nào đang chờ đăng."
        items={ready.map((video) => ({
          key: String(video.id),
          video,
          sub: `${video.created_by} · tạo ${formatDateTime(video.created_at)}`,
          href: publishHref(video.id),
          action: "Đăng",
        }))}
      />
    </div>
  );
}

type Suggestion = { key: string; video: VideoRow; sub: string; href: string; action: string };

function SuggestionCard({
  testId,
  title,
  help,
  empty,
  items,
}: {
  testId: string;
  title: string;
  help: string;
  empty: string;
  items: Suggestion[];
}) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, SHORT);
  return (
    <Card
      size="small"
      data-testid={testId}
      // min-width 0: a long Page name in a button must not push the card past its column.
      style={{ flex: 1, minWidth: 0 }}
      title={
        <Flex vertical style={{ padding: "8px 0" }}>
          <span>
            {title}
            {items.length > 0 && ` (${items.length})`}
          </span>
          <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: "normal", whiteSpace: "normal" }}>
            {help}
          </Typography.Text>
        </Flex>
      }
    >
      {items.length === 0 ? (
        <Typography.Text type="secondary">{empty}</Typography.Text>
      ) : (
        <Flex vertical gap={10}>
          {shown.map((item) => (
            <Flex key={item.key} align="center" justify="space-between" gap={12} wrap data-testid="suggestion">
              <div style={{ minWidth: 220, flex: 1 }}>
                <VideoTitleCell
                  id={item.video.id}
                  title={item.video.title || item.video.topic}
                  thumbnailUrl={item.video.thumbnail_url}
                  sub={item.sub}
                  maxWidth={360}
                />
              </div>
              <Link prefetch={false} href={item.href}>
                <Button size="small" icon={<SendOutlined />} title={item.action} style={{ maxWidth: 240 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{item.action}</span>
                </Button>
              </Link>
            </Flex>
          ))}
          {items.length > SHORT && (
            <Button
              type="link"
              size="small"
              style={{ alignSelf: "flex-start", padding: 0 }}
              onClick={() => setAll(!all)}
            >
              {all ? "Thu gọn" : `Xem thêm ${items.length - SHORT}`}
            </Button>
          )}
        </Flex>
      )}
    </Card>
  );
}
