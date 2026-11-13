"use client";
import FormDrawer from "@/components/FormDrawer";
import PostComment from "@/components/PostComment";
import PostActions from "@/components/video/PostActions";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { App, Button, Flex, Spin } from "antd";
import { useState } from "react";

export default function VideoPostsButton({
  videoId,
  onChanged,
}: {
  videoId: number;
  onChanged: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [failed, setFailed] = useState(false);
  async function read() {
    try {
      setFailed(false);
      setVideo(await api<VideoDetail>(`/videos/${videoId}`));
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
          setVideo(null);
          void read();
        }}
      >
        Bình luận và bài đăng
      </Button>
      <FormDrawer title="Bình luận và bài đăng" open={open} onClose={() => setOpen(false)} footer={null}>
        {video ? (
          <Flex vertical gap={16}>
            {video.publications.map((post) => (
              <Flex vertical gap={6} key={post.id}>
                <strong>{post.fanpage}</strong>
                <PostComment post={post} onChanged={() => void changed()} />
                <PostActions post={post} disabled={video.locked} compact onDone={() => void changed()} />
              </Flex>
            ))}
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
