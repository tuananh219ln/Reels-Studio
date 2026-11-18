"use client";
import FormDrawer from "@/components/FormDrawer";
import PostComment from "@/components/PostComment";
import StatusText from "@/components/StatusText";
import { EditorContext } from "@/components/video/AutoSaveField";
import PostActions from "@/components/video/PostActions";
import { EngageContent } from "@/components/video/PostContent";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { LINK_STATES } from "@/lib/commentLinks";
import { App, Button, Card, Flex, Spin, Typography, type ButtonProps } from "antd";
import { useMemo, useState } from "react";

/**
 * "Bình luận và bài đăng" on Affiliate: the video's products and comments (the video page's "Bình luận & Sản phẩm"
 * blocks, products first), then each live post with whether its comment on Facebook holds a link, so a member finds
 * what is missing and adds it without leaving the list (decisions/2026-11-18-affiliate-comment-links.md).
 */
export default function VideoPostsButton({
  videoId,
  onChanged,
  label = "Bình luận và bài đăng",
  type,
  icon,
}: {
  videoId: number;
  onChanged: () => void | Promise<void>;
  label?: string;
  type?: ButtonProps["type"];
  icon?: ButtonProps["icon"];
}) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [failed, setFailed] = useState(false);
  // Whether anything was saved, so the list reloads once when the drawer closes, not on every keystroke.
  const [dirty, setDirty] = useState(false);

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
  function close() {
    setOpen(false);
    if (dirty) {
      setDirty(false);
      void onChanged();
    }
  }

  // The blocks save field by field, as on the video page; here they never wait on a render or an edit mode.
  const editor = useMemo(
    () => ({
      locked: video?.locked ?? false,
      readOnly: false,
      reportFailed: () => undefined,
      track: () => undefined,
      flush: async () => undefined,
      onSaved: (saved: VideoDetail) => {
        setVideo(saved);
        setDirty(true);
      },
    }),
    [video?.locked],
  );

  const posts = video?.publications;

  return (
    <>
      <Button
        size="small"
        type={type}
        icon={icon}
        onClick={() => {
          setOpen(true);
          setVideo(null);
          void read();
        }}
      >
        {label}
      </Button>
      <FormDrawer title="Bình luận và bài đăng" open={open} onClose={close} footer={null}>
        {video && posts ? (
          <Flex vertical gap={12}>
            <EditorContext.Provider value={editor}>
              <EngageContent video={video} productsFirst />
            </EditorContext.Provider>
            <Card size="small" title="Bài đăng" style={{ borderRadius: 10 }} data-testid="drawer-posts">
              <Flex vertical gap={16}>
                {posts.length === 0 && <Typography.Text type="secondary">Video chưa có bài đăng nào.</Typography.Text>}
                {posts.map((post) => {
                  const links = post.comment.links ?? "unknown";
                  const state = LINK_STATES[links];
                  return (
                    <Flex vertical gap={6} key={post.id}>
                      <Flex wrap gap={8} align="center">
                        <strong>{post.fanpage}</strong>
                        {links !== "off" && (
                          <StatusText tone={state.tone} data-testid="post-links">
                            {state.label.charAt(0).toUpperCase() + state.label.slice(1)}
                          </StatusText>
                        )}
                      </Flex>
                      <PostComment post={post} onChanged={() => void changed()} />
                      <PostActions post={post} disabled={video.locked} compact onDone={() => void changed()} />
                    </Flex>
                  );
                })}
              </Flex>
            </Card>
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
