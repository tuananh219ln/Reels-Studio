"use client";

import { CloudUploadOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Popconfirm, Select, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  api,
  errorMessage,
  formatDateTime,
  fromVietnamInput,
  vietnamInputValue,
  type ManualPost,
  type VideoDetail,
  type YouTubeConnection,
} from "@/lib/api";
import { myPageOfGroup } from "@/lib/lastChoices";
import StatusText from "@/components/StatusText";
import { useEditor } from "./AutoSaveField";
import { useMe } from "@/components/MeContext";

export type ManualPlatform = "youtube" | "instagram";

const NAMES: Record<ManualPlatform, { label: string; placeholder: string; app: string }> = {
  youtube: { label: "YouTube Shorts", placeholder: "https://youtube.com/shorts/…", app: "YouTube" },
  instagram: { label: "Instagram Reels", placeholder: "https://www.instagram.com/reel/…", app: "Instagram" },
};

/** The Facebook slots (Vietnam time) a planned YouTube time defaults to when the video has no Facebook time ahead. */
const FACEBOOK_SLOTS = ["07:00", "11:00", "18:00"];
const TITLE_MAX = 100;

/** When the member means to make the upload public: the video's Facebook post time when it is still ahead, else the
 * next Facebook slot from now, as a `datetime-local` value in Vietnam time. */
function defaultPlanned(video: VideoDetail): string {
  const now = Date.now();
  const facebook = video.publications
    .filter((post) => post.status === "scheduled" && post.scheduled_at && Date.parse(post.scheduled_at) > now)
    .map((post) => post.scheduled_at as string)
    .sort()[0];
  if (facebook) return vietnamInputValue(facebook);
  for (let day = 0; day < 2; day++) {
    const date = vietnamInputValue(new Date(now + day * 86_400_000).toISOString()).slice(0, 10);
    for (const slot of FACEBOOK_SLOTS) {
      const value = `${date}T${slot}`;
      if (Date.parse(fromVietnamInput(value)) > now) return value;
    }
  }
  return "";
}

/**
 * A platform the app does not post to publicly (YouTube Shorts, Instagram Reels): the member downloads the MP4, copies
 * the caption, posts in the platform's own app, then records the post here with its link ("Đã đăng tay"). YouTube also
 * takes the MP4 straight from the app, private, to a channel the member connected; they make it public in YouTube
 * Studio at the time they planned.
 */
export default function ManualPostCard({ video, platform }: { video: VideoDetail; platform: ManualPlatform }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const { me } = useMe();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const names = NAMES[platform];
  const posts = video.manual_posts.filter((post) => post.platform === platform);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success("Đã chép caption + hashtag");
    } catch {
      message.error("Trình duyệt không cho chép, hãy chép tay ở thẻ Nội dung đăng");
    }
  }

  async function record() {
    setBusy(true);
    try {
      onSaved(await api<VideoDetail>(`/manual-posts/videos/${video.id}`, "POST", { platform, url }));
      setUrl("");
      message.success(`Đã ghi bài ${names.label}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(postId: number) {
    try {
      onSaved(await api<VideoDetail>(`/manual-posts/${postId}`, "DELETE"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Flex vertical gap={12} data-testid={`manual-post-${platform}`}>
      {platform === "youtube" && <YouTubeUpload video={video} />}
      <Typography.Text type="secondary">
        {platform === "youtube"
          ? "Hoặc đăng tay: tải MP4 về, chép caption rồi đăng trong app YouTube. Đăng xong dán link bài vào đây để cả nhóm biết video đã lên YouTube Shorts."
          : `App chưa kết nối ${names.app}: tải MP4 về, chép caption rồi đăng trong app ${names.app}. Đăng xong dán link bài vào đây để cả nhóm biết video đã lên ${names.label}.`}
      </Typography.Text>
      <Flex wrap gap={8}>
        {video.mp4 && (
          <Button icon={<DownloadOutlined />} href={video.mp4.download_url}>
            Tải MP4
          </Button>
        )}
        <Button icon={<CopyOutlined />} onClick={() => void copy(video.post_text)}>
          Copy caption + hashtag
        </Button>
      </Flex>
      <div>
        <Typography.Text strong>Đã đăng tay</Typography.Text>
        <Flex wrap gap={8} style={{ marginTop: 4 }}>
          <Input
            aria-label={`Link bài ${names.label}`}
            placeholder={names.placeholder}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            style={{ maxWidth: 360 }}
          />
          <Button loading={busy} disabled={!url.trim() || !video.mp4} onClick={() => void record()}>
            Ghi bài đã đăng
          </Button>
        </Flex>
      </div>
      {posts.length > 0 && (
        <Flex vertical gap={6}>
          {posts.map((post) => (
            <Flex key={post.id} gap={8} align="center" wrap data-testid="manual-post">
              <PostState post={post} label={names.label} />
              <Typography.Text type="secondary">
                {post.channel ? `${post.channel} · ` : ""}
                {post.created_by}, {formatDateTime(post.at)}
              </Typography.Text>
              {post.created_by_id === me.id && post.status !== "pending" && (
                <Popconfirm
                  title="Xoá bài này khỏi app?"
                  description={`Bài trên ${names.app} không bị xoá.`}
                  okText="Xoá"
                  cancelText="Huỷ"
                  onConfirm={() => void remove(post.id)}
                >
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="Xoá bài khỏi app" />
                </Popconfirm>
              )}
            </Flex>
          ))}
        </Flex>
      )}
    </Flex>
  );
}

/** One post's line: its link, and for a YouTube upload where it stands (uploading, private until made public). */
function PostState({ post, label }: { post: ManualPost; label: string }) {
  if (post.status === "pending") {
    return <StatusText tone="idle">Đang tải lên YouTube…</StatusText>;
  }
  if (post.status === "private") {
    return (
      <>
        <StatusText tone="warning">
          Đã tải lên riêng tư
          {post.planned_at ? ` · nhớ công khai lúc ${formatDateTime(post.planned_at)}` : " · chưa công khai"}
        </StatusText>
        {post.studio_url && (
          <a href={post.studio_url} target="_blank" rel="noreferrer">
            Mở YouTube Studio ↗
          </a>
        )}
      </>
    );
  }
  return (
    <a href={post.url ?? undefined} target="_blank" rel="noreferrer">
      Xem bài {label}
    </a>
  );
}

/** "Tải lên YouTube": the MP4 goes to one of the member's connected channels as a private video, with a title and the
 * time they mean to make it public (a reminder; YouTube is not told). */
function YouTubeUpload({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const { me } = useMe();
  const [connections, setConnections] = useState<YouTubeConnection[] | null>(null);
  const [channelId, setChannelId] = useState<number | null>(null);
  const [title, setTitle] = useState(() => (video.title || video.topic).slice(0, TITLE_MAX));
  const [planned, setPlanned] = useState(() => defaultPlanned(video));
  const [busy, setBusy] = useState(false);
  const uploading = video.manual_posts.some((post) => post.platform === "youtube" && post.status === "pending");

  useEffect(() => {
    let live = true;
    api<YouTubeConnection[]>("/youtube/connections").then(
      (rows) => {
        if (!live) return;
        const usable = rows.filter((row) => !row.needs_reconnect);
        setConnections(rows);
        // The channel of the member's Page for the video's group, else their only channel.
        const pageId = myPageOfGroup(video, me.id);
        const ofPage = video.fanpages.find((page) => page.id === pageId)?.youtube_channel_id ?? null;
        const picked = usable.find((row) => row.channel_id === ofPage) ?? (usable.length === 1 ? usable[0] : null);
        setChannelId((current) => current ?? picked?.channel_id ?? null);
      },
      () => live && setConnections([]),
    );
    return () => {
      live = false;
    };
    // Once per video: a member's own pick is never overwritten by a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reads the video only to pick a default when it opens
  }, [video.id]);

  async function send() {
    if (channelId === null) return;
    setBusy(true);
    try {
      const saved = await api<VideoDetail>(`/youtube/videos/${video.id}/upload`, "POST", {
        channel_id: channelId,
        title,
        planned_at: planned ? fromVietnamInput(planned) : null,
      });
      onSaved(saved);
      message.success("Đang tải video lên YouTube ở chế độ riêng tư");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const usable = (connections ?? []).filter((row) => !row.needs_reconnect);
  return (
    <Flex vertical gap={8} data-testid="youtube-upload">
      <Typography.Text strong>Tải lên YouTube (riêng tư)</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        App tải MP4 lên kênh của bạn ở chế độ riêng tư. Đến giờ dự định, bạn tự công khai hoặc hẹn giờ trong YouTube
        Studio; app chỉ nhắc giờ và tự nhận ra khi video đã công khai.
      </Typography.Text>
      {connections !== null && usable.length === 0 ? (
        <Typography.Text type="warning">
          Bạn chưa kết nối kênh YouTube nào: bấm Kết nối YouTube ở Quản lý kênh.
        </Typography.Text>
      ) : (
        <>
          <Select
            aria-label="Kênh YouTube"
            placeholder="Chọn kênh YouTube"
            loading={connections === null}
            value={channelId}
            onChange={(value: number) => setChannelId(value)}
            options={usable.map((row) => ({ value: row.channel_id, label: row.title }))}
            style={{ maxWidth: 360 }}
          />
          <Input
            aria-label="Tiêu đề YouTube"
            placeholder="Tiêu đề video trên YouTube"
            value={title}
            maxLength={TITLE_MAX}
            showCount
            onChange={(event) => setTitle(event.target.value)}
            style={{ maxWidth: 480 }}
          />
          <Flex wrap gap={8} align="center">
            <Typography.Text>Dự định công khai lúc</Typography.Text>
            <Input
              aria-label="Giờ dự định công khai"
              type="datetime-local"
              value={planned}
              onChange={(event) => setPlanned(event.target.value)}
              style={{ width: 220 }}
            />
          </Flex>
          <div>
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={busy || uploading}
              disabled={!video.mp4 || channelId === null || !title.trim() || video.locked}
              onClick={() => void send()}
            >
              {uploading ? "Đang tải lên…" : "Tải lên YouTube"}
            </Button>
          </div>
        </>
      )}
    </Flex>
  );
}
