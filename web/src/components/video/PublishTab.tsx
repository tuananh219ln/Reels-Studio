"use client";

import { DownloadOutlined } from "@ant-design/icons";
import { Button, Card, Flex, Typography } from "antd";
import { useEffect, useRef, type ContextType } from "react";
import ApproveVideoButton from "@/components/actions/ApproveVideoButton";
import ListenVolume, { listenNow, setListen, useListen } from "@/components/ListenVolume";
import { formatDecimal, type VideoDetail } from "@/lib/api";
import { EditorContext } from "./AutoSaveField";
import PostContent from "./PostContent";
import PublishCard, { PublishButton } from "./PublishCard";
import QcGrid, { QcBadge } from "./QcCard";

/**
 * The "Đăng bài" tab, in the order a member goes through it: is the MP4 ready (QC, download, post), the post's texts,
 * then the rarer blocks closed, then where it has been posted.
 */
export default function PublishTab({
  video,
  postEditor,
  onApproved,
}: {
  video: VideoDetail;
  /** The post texts stay editable while the page is in "Xem". */
  postEditor: ContextType<typeof EditorContext>;
  onApproved: () => void;
}) {
  return (
    <Flex vertical gap={12} data-testid="publish-tab">
      <ReadyCard video={video} onApproved={onApproved} />
      <EditorContext.Provider value={postEditor}>
        <PostContent video={video} />
      </EditorContext.Provider>
      <PublishCard video={video} />
    </Flex>
  );
}

/** "Sẵn sàng đăng?": the QC tiles, the MP4 and its facts, and "Tải MP4" beside "Đăng bài". */
function ReadyCard({ video, onApproved }: { video: VideoDetail; onApproved: () => void }) {
  const mp4 = video.mp4;
  if (!mp4) {
    return (
      <Card size="small" title="Sẵn sàng đăng?">
        <Typography.Text type="secondary">
          Chưa có MP4. Bấm “Render” khi các cảnh đã đủ ảnh; MP4 và nút “Đăng bài” (Facebook, TikTok, YouTube Shorts,
          Instagram Reels) sẽ hiện ở đây.
        </Typography.Text>
      </Card>
    );
  }
  return (
    <Card size="small" title="Sẵn sàng đăng?" extra={mp4.qc && <QcBadge qc={mp4.qc} />} data-testid="ready-card">
      <Flex vertical gap={10}>
        {mp4.qc && <QcGrid qc={mp4.qc} />}
        <Flex gap={8}>
          <Button icon={<DownloadOutlined />} href={mp4.download_url} style={{ flex: 1 }}>
            Tải MP4
          </Button>
          <div style={{ flex: 1 }}>
            <PublishButton video={video} block />
          </div>
        </Flex>
        {video.post_stage === "ready" && video.plan_idea?.suggested_post_at && (
          <ApproveVideoButton videoId={video.id} onDone={onApproved} />
        )}
        <Flex gap={12} align="flex-start">
          <Mp4Player key={mp4.url} url={mp4.url} />
          <Typography.Text type="secondary" style={{ fontSize: 13 }} data-testid="render-time">
            Dài {formatDecimal(mp4.seconds)} giây, render mất {formatDecimal(mp4.render_seconds)} giây
          </Typography.Text>
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
