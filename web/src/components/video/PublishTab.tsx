"use client";

import { DownloadOutlined } from "@ant-design/icons";
import { Button, Card, Flex, Typography } from "antd";
import { useEffect, useRef, type ContextType } from "react";
import ApproveVideoButton from "@/components/actions/ApproveVideoButton";
import ListenVolume, { listenNow, setListen, useListen } from "@/components/ListenVolume";
import { formatDecimal, type VideoDetail } from "@/lib/api";
import { EditorContext } from "./AutoSaveField";
import PostContent, { type PostTabKey } from "./PostContent";
import PostComment from "@/components/PostComment";
import StatusText from "@/components/StatusText";
import { POST_STATUS } from "@/lib/postStatus";
import { PostRows, PublishButton } from "./PublishCard";
import { QcStrip } from "./QcCard";

/**
 * The side panel, in the order a member goes through it: the MP4 with "Tải MP4" and "Đăng bài" (its QC is the chip in
 * the page's header), the post's texts in one tile with tabs, then where it has been posted.
 */
export default function PublishTab({
  video,
  postEditor,
  onApproved,
  tab,
  onTab,
  fit = false,
}: {
  video: VideoDetail;
  /** The post texts stay editable while the page is in "Xem". */
  postEditor: ContextType<typeof EditorContext>;
  onApproved: () => void;
  /** The tab of the post texts; the page sets it when a step of the progress line points at one. */
  tab?: PostTabKey;
  onTab?: (tab: PostTabKey) => void;
  /** The panel is as tall as the screen: the post texts take what the other tiles leave and scroll inside. */
  fit?: boolean;
}) {
  return (
    <Flex vertical gap={12} data-testid="publish-tab" style={fit ? { height: "100%" } : undefined}>
      <div style={fit ? { flex: "none", maxHeight: "55%", overflowY: "auto" } : undefined}>
        <ReadyCard video={video} onApproved={onApproved} />
      </div>
      <div style={fit ? { flex: "1 1 0", minHeight: 160, overflowY: "auto" } : undefined}>
        <EditorContext.Provider value={postEditor}>
          <PostContent video={video} tab={tab} onTab={onTab} />
        </EditorContext.Provider>
      </div>
    </Flex>
  );
}

/** "Sẵn sàng đăng?": where the video stands on posting, its QC as one line, the MP4 small beside its facts and, per
 * place, each post as a tinted row (green out, amber waiting, red failed), then "Tải MP4" and "Đăng bài". */
function ReadyCard({ video, onApproved }: { video: VideoDetail; onApproved: () => void }) {
  const mp4 = video.mp4;
  const hasPosts = video.publications.length + video.tiktok_posts.length + video.manual_posts.length > 0;
  if (!mp4) {
    return (
      <Card size="small" title="Sẵn sàng đăng?">
        <Flex vertical gap={8}>
          <Typography.Text type="secondary">
            Chưa có MP4. Bấm “Render” khi các cảnh đã đủ ảnh; MP4 và nút “Đăng bài” (Facebook, TikTok, YouTube Shorts,
            Instagram Reels) sẽ hiện ở đây.
          </Typography.Text>
          {hasPosts && <PostRows video={video} />}
        </Flex>
      </Card>
    );
  }
  // The newest Facebook post that is out or due carries the comment line.
  const open = video.publications.find((post) => post.status === "published" || post.status === "scheduled");
  const shown = video.publications.find((post) => post.status === "published")
    ? POST_STATUS.published
    : open
      ? POST_STATUS.scheduled
      : null;
  const reload = () => undefined;
  return (
    <Card size="small" title="Sẵn sàng đăng?" data-testid="ready-card">
      <Flex vertical gap={8}>
        {shown && (
          <StatusText tone={shown.tone} style={{ fontWeight: 600 }} data-testid="post-state">
            {shown.label}
          </StatusText>
        )}
        {mp4.qc && <QcStrip qc={mp4.qc} />}
        <Flex gap={12} align="flex-start" wrap>
          <Mp4Player key={mp4.url} url={mp4.url} />
          <Flex vertical gap={8} style={{ flex: "1 1 220px", minWidth: 0 }}>
            <Typography.Text type="secondary" style={{ fontSize: 13 }} data-testid="render-time">
              Dài {formatDecimal(mp4.seconds)} giây, render mất {formatDecimal(mp4.render_seconds)} giây
            </Typography.Text>
            <PostRows video={video} />
            {open && (
              <div data-testid="post-comment-state">
                <PostComment post={open} onChanged={reload} readOnly />
              </div>
            )}
            <Flex gap={8} wrap>
              <Button icon={<DownloadOutlined />} href={mp4.download_url}>
                Tải MP4
              </Button>
              <PublishButton video={video} />
            </Flex>
            {video.post_stage === "ready" && video.plan_idea?.suggested_post_at && (
              <ApproveVideoButton videoId={video.id} onDone={onApproved} />
            )}
          </Flex>
        </Flex>
      </Flex>
    </Card>
  );
}

/** The MP4 small beside its facts, with the listener's volume under it: at this width the browser's own controls
 * keep only a mute button. */
function Mp4Player({ url }: { url: string }) {
  const player = useRef<HTMLVideoElement>(null);
  const { level, muted } = useListen();
  useEffect(() => {
    if (!player.current) return;
    player.current.volume = level;
    player.current.muted = muted;
  }, [level, muted]);
  return (
    <Flex vertical gap={4} style={{ flex: "none", width: 120 }}>
      <video
        ref={player}
        src={url}
        controls
        preload="metadata"
        data-testid="mp4-player"
        // The browser's own mute button moves the shared level too, so every player stays in step.
        onVolumeChange={(event) => {
          const { volume, muted: silent } = event.currentTarget;
          const now = listenNow();
          if (Math.abs(volume - now.level) > 0.001 || silent !== now.muted) setListen({ level: volume, muted: silent });
        }}
        style={{ width: 120, aspectRatio: "9 / 16", background: "#000", borderRadius: 8 }}
      />
      <ListenVolume width={80} />
    </Flex>
  );
}
