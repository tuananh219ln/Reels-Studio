"use client";

import { SendOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Checkbox, Flex, Input, Radio, Select, Tag, Typography } from "antd";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type Post, type VideoDetail } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import { useEditor } from "./AutoSaveField";
import PostActions from "./PostActions";
import PostMetrics from "@/components/PostMetrics";
import PostComment from "@/components/PostComment";
import FormDrawer from "@/components/FormDrawer";

// TikTok and YouTube need their own app review first (docs/project.md), so they are shown but cannot be picked yet.
const PLATFORMS = [
  { value: "facebook", label: "Facebook" },
  { value: "tiktok", label: "TikTok (sắp có)", disabled: true },
  { value: "youtube", label: "YouTube (sắp có)", disabled: true },
];

/** "Đăng" in the MP4 block: posts the current MP4 with the saved caption and hashtags to one of the team's Fanpages. */
export function PublishButton({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  // /videos/<id>?publish=<fanpage id>: a suggestion on "Bài đăng" opens the dialog, with that Page picked if given.
  // The button mounts once the video has loaded in the browser, so the address is there to read.
  const [asked] = useState(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("publish"),
  );
  const [open, setOpen] = useState(asked !== null);
  const [mode, setMode] = useState<"now" | "later">("now");
  const [when, setWhen] = useState("");
  const [picked, setPicked] = useState<number | null>(() =>
    video.fanpages.some((page) => page.id === Number(asked)) ? Number(asked) : null,
  );
  const router = useRouter();
  const pathname = usePathname();
  // Drop the request from the address, so a reload does not open the dialog again.
  useEffect(() => {
    if (asked !== null) router.replace(pathname);
  }, [asked, router, pathname]);
  const [autoComment, setAutoComment] = useState(true);
  const [busy, setBusy] = useState(false);
  const fanpage = picked ?? (video.fanpages.length === 1 ? video.fanpages[0].id : null);
  const chosen = video.fanpages.find((page) => page.id === fanpage);
  const name = chosen?.name;
  const sameMp4 = fanpage !== null && video.posted_fanpage_ids.includes(fanpage);
  const oldPost = video.publications.some(
    (post) => post.fanpage === name && (post.status === "scheduled" || post.status === "published"),
  );

  async function publish() {
    setBusy(true);
    try {
      // The post uses the saved caption: leave the field being typed in and wait until it is saved.
      await editor.flush();
      const scheduled_at = mode === "later" ? new Date(when).toISOString() : null;
      editor.onSaved(
        await api<VideoDetail>(`/videos/${video.id}/publish`, "POST", {
          fanpage_id: fanpage,
          scheduled_at,
          auto_comment: autoComment,
        }),
      );
      setOpen(false);
      // The next post starts fresh: a time kept from this one would schedule it by mistake.
      setMode("now");
      setWhen("");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const waiting = !fanpage || (mode === "later" && !when) || sameMp4 || video.mp4_outdated || video.locked;
  return (
    <>
      <Button type="primary" icon={<SendOutlined />} disabled={video.locked} onClick={() => setOpen(true)}>
        Đăng
      </Button>
      <FormDrawer
        title="Đăng video"
        open={open}
        onClose={() => setOpen(false)}
        okText="Đăng"
        cancelText="Huỷ"
        onOk={publish}
        confirmLoading={busy}
        okButtonProps={{ disabled: waiting }}
      >
        {video.fanpages.length === 0 ? (
          <Typography.Text>
            Chưa có Fanpage nào đang dùng. Vào{" "}
            <Link prefetch={false} href="/fanpages">
              Kết nối Fanpage
            </Link>{" "}
            để thêm.
          </Typography.Text>
        ) : (
          <Flex vertical gap={8}>
            {video.mp4_outdated && <Alert type="warning" showIcon title="Hãy render lại trước khi đăng" />}
            {sameMp4 && (
              <Alert
                type="error"
                showIcon
                title="Bản MP4 này đang có trên Fanpage đó. Hãy render bản mới hoặc xóa bài cũ."
              />
            )}
            {chosen?.error && (
              <Alert type="warning" showIcon title={`Lần kiểm tra gần nhất, Fanpage này lỗi: ${chosen.error}`} />
            )}
            {oldPost && !sameMp4 && (
              <Alert type="warning" showIcon title="Fanpage này vẫn còn bài cũ của video. Đăng thêm sẽ có hai bài." />
            )}
            <Select aria-label="Nền tảng" value="facebook" options={PLATFORMS} style={{ maxWidth: 320 }} />
            <Select
              aria-label="Fanpage"
              value={fanpage}
              placeholder="Chọn Fanpage"
              onChange={setPicked}
              style={{ maxWidth: 320 }}
              options={video.fanpages.map((page) => ({
                value: page.id,
                label: page.owner ? `${page.name} · ${page.owner}` : page.name,
              }))}
            />
            <Radio.Group
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              options={[
                { value: "now", label: "Đăng ngay" },
                { value: "later", label: "Hẹn giờ" },
              ]}
            />
            {mode === "later" && (
              <Input
                type="datetime-local"
                aria-label="Giờ đăng"
                value={when}
                style={{ maxWidth: 240 }}
                onChange={(event) => setWhen(event.target.value)}
              />
            )}
            <Checkbox checked={autoComment} onChange={(event) => setAutoComment(event.target.checked)}>
              Tự bình luận khi bài lên (bình luận ghim kèm link sản phẩm Shopee đã chọn)
            </Checkbox>
            <Typography.Text type="secondary">
              Đăng bản MP4 mới nhất kèm caption và hashtag đã lưu. Facebook không cho ghim bằng API, nên vẫn ghim bình
              luận tay trên Facebook.
            </Typography.Text>
          </Flex>
        )}
      </FormDrawer>
    </>
  );
}

function statusText(post: Post): string {
  if (post.status === "published") return "Đã đăng lên Facebook";
  if (post.status === "scheduled" && post.scheduled_at) return `Đã hẹn đăng lúc ${formatDateTime(post.scheduled_at)}`;
  return POST_STATUS[post.status].label;
}

/** Every post of this video, newest first; those cancelled or deleted stay, with who did it and when. */
export default function PublishCard({ video }: { video: VideoDetail }) {
  const editor = useEditor();
  const { onSaved } = editor;
  const reload = useCallback(() => {
    api<VideoDetail>(`/videos/${video.id}`).then(onSaved, () => undefined);
  }, [video.id, onSaved]);
  if (video.publications.length === 0) return null;
  return (
    <Card title="Bài đăng của video" size="small">
      <Flex vertical gap={12}>
        {video.publications.map((post, index) => (
          <Flex key={post.id} justify="space-between" align="center" gap={8} wrap data-testid="video-post">
            <div style={{ minWidth: 0 }}>
              <Tag color={POST_STATUS[post.status].color}>{POST_STATUS[post.status].label}</Tag>
              <Typography.Text data-testid={index === 0 ? "publication-status" : undefined}>
                {statusText(post)}
              </Typography.Text>{" "}
              {post.url && (
                <a href={post.url} target="_blank" rel="noreferrer">
                  Xem Reel
                </a>
              )}
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                {[post.fanpage, post.created_by].filter(Boolean).join(" · ")}
                {post.closed_at &&
                  ` · ${POST_STATUS[post.status].label} lúc ${formatDateTime(post.closed_at)} ${post.closed_by ? `bởi ${post.closed_by}` : "trên Facebook"}`}
              </Typography.Paragraph>
              <PostMetrics post={post} />
              <PostComment post={post} onChanged={reload} />
            </div>
            <PostActions post={post} disabled={video.locked} onDone={editor.onSaved} />
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}
