"use client";

import { COLORS } from "@/app/theme";
import StatusText from "@/components/StatusText";
import { PostedPlatforms, VideoKindTags } from "@/components/VideoKind";
import VideoStatusTags from "@/components/VideoStatusTags";
import WinnerFlag from "@/components/WinnerFlag";
import { formatDateTime, type VideoRow, type VideoRowPost } from "@/lib/api";
import { videoStatusLabel, videoStatusTone } from "@/lib/videoStatus";
import { Flex, theme, Typography } from "antd";
import Link from "next/link";
import { percent, STANDOUT_TIMES, wantsTikTok } from "./format";

/** A small rounded link inside a card or row, which may itself be a link: it opens its own page, not the card's. */
export function CardChip({
  href,
  label,
  testId,
  children,
}: {
  href: string;
  label: string;
  testId: string;
  children: React.ReactNode;
}) {
  const { token } = theme.useToken();
  return (
    <Link
      href={href}
      prefetch={false}
      aria-label={label}
      data-testid={testId}
      onClick={(event) => event.stopPropagation()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "0 8px",
        lineHeight: "22px",
        borderRadius: 11,
        border: `1px solid ${token.colorBorderSecondary}`,
        fontSize: 12,
        color: "inherit",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </Link>
  );
}

/** "TikTok" with its status ("Nháp", "Đã đăng"): the versions of a video, each opening its own page. */
export function VersionLinks({ versions }: { versions: VideoRow[] }) {
  const { token } = theme.useToken();
  return versions.map((version) => (
    <CardChip
      key={version.id}
      href={`/videos/${version.id}`}
      label={`Mở bản TikTok: ${version.name || version.title || version.topic}`}
      testId="video-version"
    >
      <span style={{ color: token.colorTextSecondary }}>TikTok</span>
      <StatusText tone={version.tiktok_posted ? "success" : videoStatusTone(version)}>
        {version.tiktok_posted ? "Đã đăng" : videoStatusLabel(version)}
      </StatusText>
    </CardChip>
  ));
}

/** The "Trạng thái" cell of every video table: the status and where it is out, its kind, the winner flag, and the
 * TikTok versions (or the offer to make one). */
export function VideoStatusCell({
  row,
  versions = [],
  onChanged,
}: {
  row: VideoRow;
  versions?: VideoRow[];
  onChanged?: () => void;
}) {
  return (
    <Flex vertical gap={4} align="flex-start">
      <Flex gap={8} align="center" wrap>
        <VideoStatusTags video={row} />
        <PostedPlatforms postedOn={row.posted_on} links={row.posted_links} states={row.posted_states} />
      </Flex>
      <VideoKindTags video={row} />
      <WinnerFlag video={row} onChanged={onChanged} />
      <VersionLinks versions={versions} />
      {wantsTikTok(row) && (
        <Link href={`/videos/${row.id}?clone=tiktok`} onClick={(event) => event.stopPropagation()}>
          Tạo bản TikTok
        </Link>
      )}
    </Flex>
  );
}

/** The "Số liệu" cell of every video table: "N view", then "48h: x× trung vị, y% share". A video that is not out, or
 * not read yet, shows a dash, never a zero it does not have. */
export function VideoNumbersCell({ post }: { post: VideoRowPost | null }) {
  if (!post || (post.views === null && post.times_median === null && post.share_rate === null)) {
    return <Typography.Text type="secondary">—</Typography.Text>;
  }
  const standout = post.times_median !== null && post.times_median >= STANDOUT_TIMES;
  return (
    <Flex vertical>
      <Typography.Text strong>
        {post.views !== null ? `${post.views.toLocaleString("vi-VN")} view` : "— view"}
      </Typography.Text>
      <Typography.Text
        type={standout ? undefined : "secondary"}
        strong={standout}
        style={{ fontSize: 12, ...(standout ? { color: COLORS.primary } : {}) }}
      >
        {post.times_median !== null
          ? `48h: ${post.times_median.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}×`
          : "48h: chưa đủ dữ liệu"}
        {post.share_rate !== null && `, ${percent(post.share_rate)} share`}
      </Typography.Text>
    </Flex>
  );
}

/** The "Tạo" cell of every video table: who made it and when; the group and plan day under it when `group` (a list
 * across groups). */
export function VideoMadeCell({ row, group = false }: { row: VideoRow; group?: boolean }) {
  return (
    <Flex vertical>
      <Typography.Text ellipsis>{row.created_by}</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {formatDateTime(row.created_at)}
      </Typography.Text>
      {group && (row.knowledge_topic || row.plan_day) && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
          {[row.knowledge_topic, row.plan_day ? `ngày ${row.plan_day}` : null].filter(Boolean).join(", ")}
        </Typography.Text>
      )}
    </Flex>
  );
}
