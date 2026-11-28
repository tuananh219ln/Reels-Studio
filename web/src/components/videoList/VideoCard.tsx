"use client";

import { COLORS } from "@/app/theme";
import VideoActions from "@/components/actions/VideoActions";
import StatusText from "@/components/StatusText";
import { PostedPlatforms, VideoKindTags } from "@/components/VideoKind";
import VideoNameEditor from "@/components/VideoNameEditor";
import VideoThumbnail from "@/components/VideoThumbnail";
import WinnerFlag from "@/components/WinnerFlag";
import type { VideoRow } from "@/lib/api";
import { videoStatusLabel, videoStatusTone } from "@/lib/videoStatus";
import { ClockCircleOutlined, EyeOutlined, PlusOutlined } from "@ant-design/icons";
import { Card, Checkbox, Flex, theme, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { CardChip, VersionLinks } from "./cells";
import { compactViews, percent, shortDate, STANDOUT_TIMES, wantsTikTok } from "./format";

/** A card on its side. The thumbnail is left as it is but for its views, in the corner as on a profile grid; the
 * text reads top to bottom: what it is, where it went, how it did, and who made it. */
export default function VideoCard({
  row,
  versions = [],
  onChanged,
  showGroup = true,
  selection,
}: {
  row: VideoRow;
  versions?: VideoRow[];
  onChanged: () => Promise<void>;
  /** The group and plan day at the foot of the card: for a list across groups. */
  showGroup?: boolean;
  /** The tick in the thumbnail's corner (bulk actions): shown on hover, and on every card once any is ticked. */
  selection?: { checked: boolean; anyChecked: boolean; onChange: (checked: boolean, shift: boolean) => void };
}) {
  const { token } = theme.useToken();
  const name = row.name || row.title || row.topic;
  // "Đổi tên" in the card's menu opens the name editor in place of the title link.
  const [renaming, setRenaming] = useState(false);
  const post = row.post;
  const standout = post?.times_median != null && post.times_median >= STANDOUT_TIMES;
  // A job's stage or a warning, said in words after the status rather than as more tags.
  const warning = row.rerender_failed ? "render lại lỗi" : row.mp4_outdated ? "MP4 chưa cập nhật theo bản sửa" : null;
  const small = { fontSize: 12, lineHeight: "18px" } as const;
  return (
    <div
      role="group"
      className="stretch-host"
      aria-label={name}
      data-testid="video-card"
      style={{ display: "flex", flex: 1, minWidth: 0 }}
    >
      <Card
        hoverable
        style={{
          flex: 1,
          minWidth: 0,
          borderColor: selection?.checked ? token.colorPrimary : token.colorBorderSecondary,
          ...(selection?.checked ? { boxShadow: `0 0 0 1px ${token.colorPrimary}` } : {}),
        }}
        styles={{ body: { padding: 12, display: "flex", gap: 14 } }}
      >
        <div style={{ position: "relative", width: 92, flex: "none" }}>
          <VideoThumbnail name={name} url={row.thumbnail_url} width={92} plain />
          {selection && (
            <Checkbox
              className={`card-select${selection.anyChecked ? " on" : ""}`}
              checked={selection.checked}
              aria-label={`Chọn video ${name}`}
              data-testid="video-card-select"
              onChange={(event) =>
                selection.onChange(event.target.checked, Boolean((event.nativeEvent as MouseEvent).shiftKey))
              }
              style={{
                position: "absolute",
                // Above the card's stretched link.
                zIndex: 2,
                left: 4,
                top: 4,
                background: "rgba(255,255,255,0.9)",
                borderRadius: 4,
                padding: 2,
              }}
            />
          )}
          {post && (post.state === "scheduled" || post.views !== null) && (
            <span
              data-testid="video-card-views"
              style={{
                position: "absolute",
                right: 4,
                bottom: 4,
                display: "inline-flex",
                alignItems: "center",
                gap: 3,
                padding: "0 4px",
                lineHeight: "16px",
                borderRadius: 4,
                background: "rgba(0, 0, 0, 0.72)",
                color: "#fff",
                fontSize: 11,
                fontWeight: 600,
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "nowrap",
              }}
            >
              {post.state === "scheduled" ? (
                <>
                  <ClockCircleOutlined /> {shortDate(post.at).slice(0, 5)}
                </>
              ) : (
                <>
                  <EyeOutlined /> {compactViews(post.views!)}
                </>
              )}
            </span>
          )}
        </div>
        <Flex vertical style={{ minWidth: 0, flex: 1 }}>
          <Flex justify="space-between" gap={4}>
            {renaming ? (
              <VideoNameEditor
                videoId={row.id}
                name={row.name}
                title={row.title || row.topic}
                maxWidth={400}
                editing
                onEditingChange={setRenaming}
                onSaved={onChanged}
              />
            ) : (
              <Link href={`/videos/${row.id}`} prefetch={false} className="stretched-link">
                <Typography.Paragraph
                  strong
                  ellipsis={{ rows: 2, tooltip: name }}
                  style={{ margin: 0, lineHeight: "20px" }}
                >
                  {name}
                </Typography.Paragraph>
              </Link>
            )}
            <VideoActions video={row} onChanged={onChanged} onRename={() => setRenaming(true)} />
          </Flex>
          {/* Its kind on the left; where it is out on the right, every platform's icon in colour once posted there. */}
          <Flex justify="space-between" align="flex-start" gap={8} style={{ marginTop: 6 }}>
            <VideoKindTags video={row} />
            <div style={{ flex: "none", paddingTop: 2 }}>
              <PostedPlatforms postedOn={row.posted_on} links={row.posted_links} states={row.posted_states} size={13} />
            </div>
          </Flex>
          {post ? (
            <div style={{ marginTop: 6 }}>
              <Typography.Text type="secondary" style={small} ellipsis={{ tooltip: post.fanpage }}>
                {post.fanpage}
                {post.pages > 1 && ` và ${post.pages - 1} trang khác`}
              </Typography.Text>
              <div>
                <Typography.Text type="secondary" style={small}>
                  {post.state === "scheduled" ? `Hẹn đăng ${shortDate(post.at)}` : `Đăng ${shortDate(post.at)}`}
                </Typography.Text>
              </div>
            </div>
          ) : (
            <Typography.Text type="secondary" style={{ ...small, marginTop: 6 }}>
              Chưa đăng
            </Typography.Text>
          )}
          <WinnerFlag video={row} onChanged={() => void onChanged()} />
          {post && (post.times_median !== null || post.share_rate !== null) && (
            <Flex gap={12} wrap style={{ marginTop: 6, ...small, fontVariantNumeric: "tabular-nums" }}>
              {post.times_median !== null && (
                <Typography.Text
                  strong={standout}
                  style={{ ...small, color: standout ? COLORS.primary : undefined }}
                  data-testid="video-card-times"
                >
                  {post.times_median.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}× trung vị
                </Typography.Text>
              )}
              {post.share_rate !== null && (
                <Typography.Text
                  type={post.share_met ? "success" : "secondary"}
                  style={small}
                  title={post.share_met ? "Đạt mục tiêu share/view" : "Chưa đạt mục tiêu share/view"}
                >
                  {percent(post.share_rate)} share
                </Typography.Text>
              )}
            </Flex>
          )}
          <Flex justify="space-between" align="flex-end" gap={8} style={{ marginTop: "auto", paddingTop: 10 }}>
            <Flex gap={10} align="center" style={small}>
              <StatusText tone={videoStatusTone(row)} data-testid="video-status">
                {videoStatusLabel(row)}
              </StatusText>
            </Flex>
            <Typography.Text type="secondary" style={{ ...small, textAlign: "right", flex: "none" }}>
              {row.created_by}, {shortDate(row.created_at, false)}
            </Typography.Text>
          </Flex>
          {(versions.length > 0 || wantsTikTok(row)) && (
            <Flex gap={6} wrap style={{ marginTop: 6 }}>
              <VersionLinks versions={versions} />
              {wantsTikTok(row) && (
                <CardChip
                  href={`/videos/${row.id}?clone=tiktok`}
                  label={`Tạo bản TikTok cho ${name}`}
                  testId="card-make-tiktok"
                >
                  <PlusOutlined style={{ color: COLORS.primary }} />
                  <span style={{ color: COLORS.primary }}>Tạo bản TikTok</span>
                </CardChip>
              )}
            </Flex>
          )}
          {/* Said on a line of its own, so the status line never breaks. */}
          {warning && (
            <Typography.Text style={{ ...small, color: token.colorWarningText }}>
              {warning[0].toUpperCase() + warning.slice(1)}
            </Typography.Text>
          )}
          {showGroup && (row.knowledge_topic || row.plan_day) && (
            <Typography.Text type="secondary" style={{ ...small, fontSize: 11 }} ellipsis>
              {row.knowledge_topic}
              {row.plan_day ? `, ngày ${row.plan_day} kế hoạch` : ""}
            </Typography.Text>
          )}
        </Flex>
      </Card>
    </div>
  );
}
