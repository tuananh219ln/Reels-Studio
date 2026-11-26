"use client";

import { App, Badge, Button, Flex, Tabs, Typography } from "antd";
import { useState, type ContextType } from "react";
import type { VideoDetail } from "@/lib/api";
import { postBlock } from "@/lib/videoStatus";
import { EditorContext } from "./AutoSaveField";
import PostContent, { EngageContent } from "./PostContent";
import ReviewCard from "./ReviewCard";
import TitleCaptionCard from "./TitleCaptionCard";
import { showsBeats } from "@/lib/strategy";
import type { PostStep } from "./postRound";
import SetupTab from "./SetupTab";
import StatusCard, { type DrawerRequest } from "./StatusCard";

export type SideTab = "post" | "engage" | "setup";

/**
 * The side panel beside the scenes: "Đăng bài" (where the video stands on posting, the caption and the hashtags),
 * "Bình luận & Sản phẩm" (the comments and the products, an orange dot on its name while no product is attached) and
 * "Thiết lập" (the video's own settings), the tabs kept at its top while it scrolls
 * (docs/decisions/2026-11-14-video-editor-spec.md, docs/decisions/2026-11-14-video-engage-tab.md).
 */
export default function PublishTab({
  video,
  postEditor,
  onApproved,
  tab,
  onTab,
  posting,
  onPost,
  onRender,
}: {
  video: VideoDetail;
  /** The post texts stay editable while the page is in "Xem". */
  postEditor: ContextType<typeof EditorContext>;
  onApproved: () => void;
  tab: SideTab;
  onTab: (tab: SideTab) => void;
  /** "Đăng lên N nền tảng" is going through its platforms. */
  posting: boolean;
  onPost: (steps: PostStep[]) => void;
  /** "Render lại", as the header's button. */
  onRender: () => void;
}) {
  const { modal } = App.useApp();
  // "Tùy chọn đăng khác", on "Đăng bài" under the status card (owner, 2026-11-15): the card's drawer opens on the
  // video's platform.
  const [drawerRequest, setDrawerRequest] = useState<DrawerRequest | null>(null);
  const moreOptions = () => setDrawerRequest({ platform: video.platform, at: Date.now() });
  return (
    <Tabs
      className="side-tabs"
      activeKey={tab}
      onChange={(key) => onTab(key as SideTab)}
      items={[
        {
          key: "post",
          label: "Đăng bài",
          forceRender: true,
          children: (
            <Flex vertical gap={12} data-testid="publish-tab">
              <EditorContext.Provider value={postEditor}>
                <ReviewCard video={video} />
                {showsBeats(video) && <TitleCaptionCard video={video} />}
              </EditorContext.Provider>
              <StatusCard
                video={video}
                onApproved={onApproved}
                posting={posting}
                onPost={onPost}
                onRender={onRender}
                drawerRequest={drawerRequest}
              />
              {/* The posting drawer with every platform's own options (a Page's queue, TikTok posted directly, a post
                  made by hand); what was posted shows on the card above once it closes. */}
              {video.mp4 && (
                <Flex vertical gap={4} align="flex-start" data-testid="publish-more">
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    Hàng chờ của Page, đăng thẳng lên TikTok, ghi lại bài đã đăng tay.
                  </Typography.Text>
                  <Button
                    disabled={video.locked || postBlock(video) !== null}
                    title={postBlock(video) ?? undefined}
                    onClick={() => {
                      // A red QC check does not stop posting, but the member says so first.
                      if (video.mp4?.qc?.status !== "fail") {
                        moreOptions();
                        return;
                      }
                      modal.confirm({
                        title: "MP4 chưa đạt kiểm tra chất lượng",
                        content: "Còn mục đỏ trong QC ở đầu trang. Nên sửa rồi render lại; vẫn đăng bản này?",
                        okText: "Vẫn đăng",
                        cancelText: "Huỷ",
                        onOk: moreOptions,
                      });
                    }}
                  >
                    Tùy chọn đăng khác
                  </Button>
                </Flex>
              )}
              <EditorContext.Provider value={postEditor}>
                <PostContent video={video} />
              </EditorContext.Provider>
            </Flex>
          ),
        },
        // Kept mounted while hidden, so a file input or a field being typed in keeps working.
        {
          key: "engage",
          label: (
            // The badge resets its text to the default colour: the label keeps the tab's own (orange when picked).
            <Badge
              dot={video.affiliate_product_ids.length === 0}
              color="orange"
              offset={[6, 0]}
              styles={{ root: { color: "inherit", fontSize: "inherit", lineHeight: "inherit" } }}
            >
              Bình luận & Sản phẩm
            </Badge>
          ),
          forceRender: true,
          children: (
            <EditorContext.Provider value={postEditor}>
              <EngageContent video={video} />
            </EditorContext.Provider>
          ),
        },
        // A finished MP4 has no voice, music, text or template to set: its tab is not there.
        ...(video.mode === "upload"
          ? []
          : [
              {
                key: "setup",
                label: "Thiết lập",
                forceRender: true,
                children: <SetupTab video={video} />,
              },
            ]),
      ]}
    />
  );
}
