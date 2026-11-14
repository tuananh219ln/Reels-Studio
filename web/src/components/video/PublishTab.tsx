"use client";

import { Badge, Flex, Tabs } from "antd";
import { useState, type ContextType } from "react";
import type { VideoDetail } from "@/lib/api";
import { EditorContext } from "./AutoSaveField";
import PostContent, { EngageContent } from "./PostContent";
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
  // "Tùy chọn đăng khác" in "Thiết lập": back on "Đăng bài", its card's drawer opens on the video's platform.
  const [drawerRequest, setDrawerRequest] = useState<DrawerRequest | null>(null);
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
              <StatusCard
                video={video}
                onApproved={onApproved}
                posting={posting}
                onPost={onPost}
                onRender={onRender}
                drawerRequest={drawerRequest}
              />
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
        {
          key: "setup",
          label: "Thiết lập",
          forceRender: true,
          children: (
            <SetupTab
              video={video}
              onMoreOptions={() => {
                onTab("post");
                setDrawerRequest({ platform: video.platform, at: Date.now() });
              }}
            />
          ),
        },
      ]}
    />
  );
}
