"use client";
import FormDrawer from "@/components/FormDrawer";
import PostComment from "@/components/PostComment";
import PostMetrics from "@/components/PostMetrics";
import PostActions from "@/components/video/PostActions";
import { api, errorMessage, type PostRow } from "@/lib/api";
import { App, Button, Flex, Spin, Typography } from "antd";
import { useEffect, useState } from "react";

/** Lazy post details keep a dashboard or an affiliate list from loading a second copy of every post. */
export default function ManagedPostActions({
  postId,
  onChanged,
  openWith,
}: {
  postId: number;
  onChanged: () => void | Promise<void>;
  /** The drawer is opened from a menu of the caller's instead of this component's own button: the caller says when,
   * and closes it again through `onClose`. */
  openWith?: { open: boolean; onClose: () => void };
}) {
  const { message } = App.useApp();
  const [ownOpen, setOwnOpen] = useState(false);
  const open = openWith ? openWith.open : ownOpen;
  const setOpen = (next: boolean) => (openWith && !next ? openWith.onClose() : setOwnOpen(next));
  const [post, setPost] = useState<PostRow | null>(null);
  const [failed, setFailed] = useState(false);
  async function read() {
    try {
      setFailed(false);
      setPost(await api<PostRow>(`/posts/${postId}`));
    } catch (err) {
      setFailed(true);
      message.error(errorMessage(err));
    }
  }
  async function changed() {
    await read();
    await onChanged();
  }
  // Opened from the caller's menu, the post is read when the drawer opens (the caller mounts this fresh each time).
  const asked = openWith?.open;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reads the post when the drawer is opened from outside
    if (asked) void read();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new opening reads again
  }, [asked]);
  return (
    <>
      {!openWith && (
        <Button
          size="small"
          onClick={() => {
            setOpen(true);
            setPost(null);
            void read();
          }}
        >
          Thao tác bài đăng
        </Button>
      )}
      <FormDrawer title="Thao tác bài đăng" open={open} onClose={() => setOpen(false)} footer={null}>
        {post ? (
          <Flex vertical gap={12}>
            <Typography.Text strong>
              {post.title}, {post.fanpage}
            </Typography.Text>
            <PostMetrics post={post} onAsked={changed} />
            <PostComment post={post} onChanged={() => void changed()} />
            <PostActions
              post={post}
              disabled={post.busy}
              compact
              onDone={() => void changed()}
              retryJobId={post.attempt?.state === "failed" ? post.attempt.job_id : null}
            />
          </Flex>
        ) : failed ? (
          <Button onClick={() => void read()}>Thử lại</Button>
        ) : (
          <Spin />
        )}
      </FormDrawer>
    </>
  );
}
