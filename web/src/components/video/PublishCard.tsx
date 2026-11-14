"use client";

import { SendOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Checkbox, Flex, Input, Radio, Select, Tabs, Typography } from "antd";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMe } from "@/components/MeContext";
import { myPages, NO_PAGE_OF_MINE, pageOptions } from "@/lib/myPages";
import { loadLastChoices, myPageOfGroup, saveLastChoice } from "@/lib/lastChoices";
import {
  api,
  errorMessage,
  formatDateTime,
  fromVietnamInput,
  vietnamInputValue,
  type Post,
  type TikTokPost,
  type VideoDetail,
} from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import { useEditor } from "./AutoSaveField";
import ManualPostCard from "./ManualPostCard";
import PostActions from "./PostActions";
import QueueButton from "./QueueButton";
import TikTokCard from "./TikTokCard";
import PostMetrics from "@/components/PostMetrics";
import FormDrawer from "@/components/FormDrawer";
import StatusText from "@/components/StatusText";

type Platform = "facebook" | "tiktok" | "youtube" | "instagram";

/**
 * "Đăng bài" in the MP4 block: one drawer for every platform the MP4 may go to, whatever platform the video was made
 * for (docs/decisions.md, 2026-11-08). Facebook: one of the team's Fanpages now, at a time, or into its queue.
 * TikTok: through the member's own connection, or recorded after posting by hand. YouTube Shorts and Instagram Reels:
 * posted by hand and recorded with their link. "Tạo bản TikTok" stays for a TikTok version with its own script.
 */
export function PublishButton({ video, block }: { video: VideoDetail; block?: boolean }) {
  const { message, modal } = App.useApp();
  const { me } = useMe();
  const editor = useEditor();
  // /videos/<id>?publish=<fanpage id>: a suggestion on "Bài đăng" opens the dialog, with that Page picked if given.
  // The button mounts once the video has loaded in the browser, so the address is there to read.
  const [asked] = useState(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("publish"),
  );
  const [open, setOpen] = useState(asked !== null);
  // A suggestion's ?publish= is a Facebook post; otherwise the drawer opens on the platform the video was made for.
  const [platform, setPlatform] = useState<Platform>(asked !== null ? "facebook" : video.platform);
  // A video of the 30-day plan starts on the time the plan means it to go out (its day, at the group's posting time).
  const planned = video.plan_idea?.suggested_post_at ?? null;
  const [mode, setMode] = useState<"now" | "later">(planned ? "later" : "now");
  const [when, setWhen] = useState(planned ? vietnamInputValue(planned) : "");
  // Only the member's own Pages can be posted to.
  const mine = myPages(video.fanpages, me.id);
  const [picked, setPicked] = useState<number | null>(() =>
    mine.some((page) => page.id === Number(asked)) ? Number(asked) : null,
  );
  const router = useRouter();
  const pathname = usePathname();
  // Drop the request from the address, so a reload does not open the dialog again.
  useEffect(() => {
    if (asked !== null) router.replace(pathname);
  }, [asked, router, pathname]);
  const [autoComment, setAutoComment] = useState(true);
  const [busy, setBusy] = useState(false);
  // The member's own Page of the video's group, else the Page they last posted to (B3), else the only one.
  const [lastPage, setLastPage] = useState<number | null>(null);
  useEffect(() => {
    if (open) loadLastChoices().then((last) => setLastPage(last.fanpage_id));
  }, [open]);
  const startPage =
    myPageOfGroup(video, me.id) ??
    (mine.some((page) => page.id === lastPage) ? lastPage : null) ??
    (mine.length === 1 ? mine[0].id : null);
  const fanpage = picked ?? startPage;
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
      const scheduled_at = mode === "later" ? fromVietnamInput(when) : null;
      editor.onSaved(
        await api<VideoDetail>(`/videos/${video.id}/publish`, "POST", {
          fanpage_id: fanpage,
          scheduled_at,
          auto_comment: autoComment,
        }),
      );
      await saveLastChoice({ fanpage_id: fanpage });
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
  const facebook =
    mine.length === 0 ? (
      <Flex vertical gap={4} align="flex-start">
        <Typography.Text data-testid="no-page-of-mine">{NO_PAGE_OF_MINE}</Typography.Text>
        <Link prefetch={false} href="/fanpages">
          Mở Quản lý Page
        </Link>
      </Flex>
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
        <Select
          aria-label="Fanpage"
          value={fanpage}
          placeholder="Chọn Fanpage"
          onChange={setPicked}
          style={{ maxWidth: 320 }}
          options={pageOptions(video.fanpages, me.id)}
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
        {mode === "later" && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Giờ Việt Nam.
            {planned && ` Kế hoạch 30 ngày gợi ý ${formatDateTime(planned)} (ngày ${video.plan_idea?.day}).`}
          </Typography.Text>
        )}
        <Checkbox checked={autoComment} onChange={(event) => setAutoComment(event.target.checked)}>
          Tự bình luận khi bài lên (bình luận ghim kèm link sản phẩm Shopee đã chọn)
        </Checkbox>
        <Typography.Text type="secondary">
          Đăng bản MP4 mới nhất kèm caption và hashtag đã lưu. Facebook không cho ghim bằng API, nên vẫn ghim bình luận
          tay trên Facebook.
        </Typography.Text>
        <Flex vertical gap={4} style={{ marginTop: 8 }}>
          <Typography.Text strong>Hoặc để Page tự đăng theo giờ</Typography.Text>
          <QueueButton video={video} />
        </Flex>
      </Flex>
    );
  const posted = {
    facebook: video.publications.filter((post) => post.status === "scheduled" || post.status === "published").length,
    tiktok: video.tiktok_posts.filter((post) => post.status !== "cancelled").length,
    youtube: video.manual_posts.filter((post) => post.platform === "youtube").length,
    instagram: video.manual_posts.filter((post) => post.platform === "instagram").length,
  };
  const label = (name: string, count: number) => (count ? `${name} (${count})` : name);
  return (
    <>
      <Button
        type="primary"
        block={block}
        icon={<SendOutlined />}
        disabled={video.locked}
        onClick={() => {
          // A red QC check does not stop posting, but the member says so first.
          if (video.mp4?.qc?.status !== "fail") {
            setOpen(true);
            return;
          }
          modal.confirm({
            title: "MP4 chưa đạt kiểm tra chất lượng",
            content: "Còn mục đỏ ở “Sẵn sàng đăng?”. Nên sửa rồi render lại; vẫn đăng bản này?",
            okText: "Vẫn đăng",
            cancelText: "Huỷ",
            onOk: () => setOpen(true),
          });
        }}
      >
        Đăng bài
      </Button>
      <FormDrawer
        title="Đăng bài"
        open={open}
        onClose={() => setOpen(false)}
        okText="Đăng"
        cancelText="Huỷ"
        onOk={publish}
        confirmLoading={busy}
        okButtonProps={{ disabled: waiting }}
        // Only Facebook posts from the drawer's own button; the other tabs carry their own.
        footer={platform === "facebook" ? undefined : null}
        width={560}
      >
        <Tabs
          activeKey={platform}
          onChange={(key) => setPlatform(key as Platform)}
          items={[
            { key: "facebook", label: label("Facebook", posted.facebook), children: facebook },
            {
              key: "tiktok",
              label: label("TikTok", posted.tiktok),
              children: <TikTokCard video={video} fanpageId={fanpage} />,
            },
            {
              key: "youtube",
              label: label("YouTube Shorts", posted.youtube),
              children: <ManualPostCard video={video} platform="youtube" />,
            },
            {
              key: "instagram",
              label: label("Instagram Reels", posted.instagram),
              children: <ManualPostCard video={video} platform="instagram" />,
            },
          ]}
        />
      </FormDrawer>
    </>
  );
}

function statusText(post: Post): string {
  if (post.status === "published") return "Đã đăng lên Facebook";
  if (post.status === "scheduled" && post.scheduled_at) return `Đã hẹn đăng lúc ${formatDateTime(post.scheduled_at)}`;
  return POST_STATUS[post.status].label;
}

const TIKTOK_STATUS: Record<TikTokPost["status"], string> = {
  pending: "Đang gửi lên TikTok",
  published: "Đã lên TikTok",
  cancelled: "Không gửi được",
};

/** Every post of this video on every platform, newest first per platform; Facebook's with their actions, the others'
 * as links (they are posted and recorded in "Đăng bài"). Cancelled or deleted Facebook posts stay, with who and when. */
export default function PublishCard({ video }: { video: VideoDetail }) {
  const editor = useEditor();
  if (video.publications.length === 0 && video.tiktok_posts.length === 0 && video.manual_posts.length === 0) {
    return null;
  }
  return (
    <Card title="Bài đăng của video" size="small">
      <Flex vertical gap={12}>
        {[
          ...video.tiktok_posts.map((post) => ({
            key: `tiktok-${post.id}`,
            label: "TikTok",
            text: [TIKTOK_STATUS[post.status], post.mode === "draft" ? "nháp trong hộp thư" : null]
              .filter(Boolean)
              .join(", "),
            url: post.url,
            who: [post.account, post.created_by, formatDateTime(post.at)].filter(Boolean).join(", "),
          })),
          ...video.manual_posts.map((post) => ({
            key: `${post.platform}-${post.id}`,
            label: post.platform_label,
            text: "Đã đăng tay",
            url: post.url,
            who: [post.created_by, formatDateTime(post.at)].join(", "),
          })),
        ].map((row) => (
          <div key={row.key} data-testid="other-post">
            <Typography.Text strong style={{ marginRight: 8 }}>
              {row.label}
            </Typography.Text>
            <Typography.Text>{row.text}</Typography.Text>{" "}
            {row.url && (
              <a href={row.url} target="_blank" rel="noreferrer">
                Xem bài
              </a>
            )}
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              {row.who}
            </Typography.Paragraph>
          </div>
        ))}
        {video.publications.map((post, index) => (
          <Flex key={post.id} justify="space-between" align="center" gap={8} wrap data-testid="video-post">
            <div style={{ minWidth: 0 }}>
              <StatusText tone={POST_STATUS[post.status].tone} style={{ marginRight: 8 }}>
                {POST_STATUS[post.status].label}
              </StatusText>
              <Typography.Text data-testid={index === 0 ? "publication-status" : undefined}>
                {statusText(post)}
              </Typography.Text>{" "}
              {post.url && (
                <a href={post.url} target="_blank" rel="noreferrer">
                  Xem Reel
                </a>
              )}
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                {[post.fanpage, post.created_by].filter(Boolean).join(", ")}
                {post.closed_at &&
                  `, ${POST_STATUS[post.status].label} lúc ${formatDateTime(post.closed_at)} ${post.closed_by ? `bởi ${post.closed_by}` : "trên Facebook"}`}
              </Typography.Paragraph>
              <PostMetrics post={post} />
            </div>
            <PostActions post={post} disabled={video.locked} onDone={editor.onSaved} />
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}
