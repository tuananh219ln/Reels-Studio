"use client";
import FormDrawer from "@/components/FormDrawer";
import PostComment from "@/components/PostComment";
import PostMetrics from "@/components/PostMetrics";
import PostActions from "@/components/video/PostActions";
import { api, errorMessage, type PostRow } from "@/lib/api";
import { App, Button, Flex, Spin, Typography } from "antd";
import { useState } from "react";

/** Lazy post details keep a dashboard or an affiliate list from loading a second copy of every post. */
export default function ManagedPostActions({
  postId,
  onChanged,
}: {
  postId: number;
  onChanged: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
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
  return (
    <>
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
