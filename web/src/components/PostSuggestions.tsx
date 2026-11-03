"use client";

import { CopyOutlined, SendOutlined } from "@ant-design/icons";
import { Button, Card, Col, Flex, Row, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, formatDateTime, type Fanpage, type PostRow, type VideoRow } from "@/lib/api";
import { formatCount } from "@/components/PostMetrics";
import VideoTitleCell from "@/components/VideoTitleCell";

/** A Page's median means something from this many measured posts (api analytics.MIN_SAMPLES). */
const MIN_SAMPLES = 5;
/** How many of each list show before "Xem thêm". */
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

type Winner = { video: VideoRow; views: number; from: string; on: Set<string> };

/** Facebook videos that did well, most viewed first: a post's views reach its Page's usual (median) views at 48
 * hours, or the Page has too few measured posts to say. `on`: the Pages the video is live or scheduled on. */
export function doingWell(videos: VideoRow[], posts: PostRow[]): Winner[] {
  const byId = new Map(videos.filter((video) => video.platform === "facebook").map((video) => [video.id, video]));
  const best = new Map<number, { views: number; from: string }>();
  for (const post of posts) {
    const views = post.metrics.at_48h?.views ?? post.metrics.latest?.views;
    if (post.status !== "published" || views === null || views === undefined || !post.fanpage) continue;
    const { median_views: median, samples } = post.metrics.analysis;
    if (samples >= MIN_SAMPLES && median !== null && views < median) continue;
    if (views > (best.get(post.video_id)?.views ?? -1)) best.set(post.video_id, { views, from: post.fanpage });
  }
  const winners: Winner[] = [];
  for (const [videoId, { views, from }] of best) {
    const video = byId.get(videoId);
    if (!video) continue;
    const on = new Set(
      posts.filter((post) => post.video_id === videoId && isActive(post) && post.fanpage).map((post) => post.fanpage!),
    );
    winners.push({ video, views, from, on });
  }
  return winners.sort((a, b) => b.views - a.views);
}

/** Three short lists above "Bài đăng": what is made and waiting to go out, and what did well on Facebook and could be
 * made again, as a TikTok version or as a variant for another of the team's Pages. Never the same MP4 on a second
 * Page: Facebook shows a copy less and can stop paying a Page that repeats content (docs/specs/multi-platform/plan.md).
 * `posts` (every post) changes when the list is reloaded, so the videos and Pages are read again with it. A failure
 * leaves the lists out: the table below still works. */
export default function PostSuggestions({ posts }: { posts: PostRow[] | null }) {
  const [videos, setVideos] = useState<VideoRow[] | null>(null);
  const [pages, setPages] = useState<Fanpage[] | null>(null);

  useEffect(() => {
    Promise.all([api<VideoRow[]>("/videos"), api<Fanpage[]>("/fanpages")])
      .then(([loadedVideos, loadedPages]) => {
        setVideos(loadedVideos);
        setPages(loadedPages);
      })
      .catch(() => setVideos(null));
  }, [posts]);

  if (!posts || !videos || !pages) return null;
  const ready = readyToPost(videos, posts);
  const winners = doingWell(videos, posts);
  const working = pages.filter((page) => page.active && !page.check.error).map((page) => page.name);
  const forTikTok = winners.filter((winner) => !winner.video.has_tiktok_version);
  const forPages = winners
    .filter((winner) => !winner.video.cloned)
    .map((winner) => ({ ...winner, missing: working.filter((name) => !winner.on.has(name)) }))
    .filter((winner) => winner.missing.length > 0);

  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
      <Col xs={24} lg={8} style={{ display: "flex" }}>
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
      </Col>
      <Col xs={24} lg={8} style={{ display: "flex" }}>
        <SuggestionCard
          testId="make-tiktok"
          title="Nên làm bản TikTok"
          help="Video chạy tốt trên Facebook (từ mức view phổ biến của Page trở lên) mà chưa có bản TikTok."
          empty="Chưa có video nào cần làm bản TikTok."
          items={forTikTok.map((winner) => ({
            key: String(winner.video.id),
            video: winner.video,
            sub: `${formatCount(winner.views)} view trên ${winner.from}`,
            href: `/videos/${winner.video.id}?clone=tiktok`,
            action: "Tạo bản TikTok",
            icon: <CopyOutlined />,
          }))}
        />
      </Col>
      <Col xs={24} lg={8} style={{ display: "flex" }}>
        <SuggestionCard
          testId="clone-for-pages"
          title="Nhân bản cho Page khác"
          help="Video chạy tốt trên một Page mà Page khác chưa có: AI viết một bản khác cho Page đó, không đăng lại cùng file."
          empty={working.length < 2 ? "Cần ít nhất 2 Fanpage đang dùng để có gợi ý." : "Chưa có video nào để nhân bản."}
          items={forPages.map((winner) => ({
            key: String(winner.video.id),
            video: winner.video,
            sub: `${formatCount(winner.views)} view trên ${winner.from} · chưa có trên ${winner.missing.join(", ")}`,
            href: `/videos/${winner.video.id}?clone=page`,
            action: "Nhân bản",
            icon: <CopyOutlined />,
          }))}
        />
      </Col>
    </Row>
  );
}

type Suggestion = {
  key: string;
  video: VideoRow;
  sub: string;
  href: string;
  action: string;
  icon?: React.ReactNode;
};

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
              {/* Takes what the button leaves; below 200 px the button goes under it instead of over it. */}
              <div style={{ minWidth: 0, flex: "1 1 200px" }}>
                <VideoTitleCell
                  id={item.video.id}
                  title={item.video.title || item.video.topic}
                  thumbnailUrl={item.video.thumbnail_url}
                  sub={item.sub}
                  maxWidth={360}
                />
              </div>
              <Link prefetch={false} href={item.href}>
                <Button size="small" icon={item.icon ?? <SendOutlined />} title={item.action} style={{ maxWidth: 240 }}>
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
