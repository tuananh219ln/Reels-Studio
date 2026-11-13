"use client";

import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import { EditorContext } from "@/components/video/AutoSaveField";
import CloneModal, { type CloneTarget } from "@/components/video/CloneModal";
import MoveGroupDrawer from "@/components/video/MoveGroupDrawer";
import { PublishButton } from "@/components/video/PublishCard";
import QueueButton from "@/components/video/QueueButton";
import type { VideoRow } from "@/lib/api";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { MoreOutlined } from "@ant-design/icons";
import { App, Button, Dropdown, Flex, Spin, Typography } from "antd";
import type { MenuProps } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";
import JobActions from "./JobActions";
import ApproveVideoButton from "./ApproveVideoButton";

/** Lists read the full current video only when an action is opened; no per-row background requests. */
export default function VideoActions({
  video,
  onChanged,
}: {
  video: Pick<VideoRow, "id" | "title" | "topic"> &
    Partial<Pick<VideoRow, "plan_day" | "post_stage" | "queue" | "suggested_post_at">>;
  onChanged?: () => void | Promise<void>;
}) {
  const { me } = useMe();
  const { message, modal } = App.useApp();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<VideoDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [clone, setClone] = useState<CloneTarget | null>(null);
  const [moving, setMoving] = useState(false);
  async function read() {
    setFailed(false);
    try {
      setDetail(await api<VideoDetail>(`/videos/${video.id}`));
    } catch (err) {
      setFailed(true);
      message.error(errorMessage(err));
    }
  }
  async function changed(next?: VideoDetail) {
    if (next) setDetail(next);
    await onChanged?.();
  }
  function remove() {
    modal.confirm({
      title: `Xóa video “${video.title || video.topic}”?`,
      content:
        "Xóa hẳn video, cảnh, job và mọi file. Không khôi phục được. Bài đã đăng hoặc hẹn giờ trên Facebook vẫn còn.",
      okText: "Xóa",
      cancelText: "Huỷ",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api(`/videos/${video.id}`, "DELETE");
          setOpen(false);
          await changed();
          message.success("Đã xóa video");
        } catch (err) {
          message.error(errorMessage(err));
          throw err;
        }
      },
    });
  }
  /** The "⋮" menu: quick actions at once; posting and the queue open a drawer, as they need their own forms. */
  function menuItems(): MenuProps["items"] {
    if (!detail) {
      return failed
        ? [{ key: "again", label: "Không tải được, thử lại", onClick: () => void read() }]
        : [{ key: "loading", label: <Spin size="small" />, disabled: true }];
    }
    const mine = detail.created_by_id === me.id;
    const posting = Boolean(detail.mp4) || Boolean(detail.active_job ?? detail.failed_job);
    return [
      { key: "open", label: "Mở video", onClick: () => router.push(`/videos/${video.id}`) },
      ...(posting ? [{ key: "post", label: "Đăng bài, hàng chờ, job…", onClick: () => setOpen(true) }] : []),
      ...(detail.mp4
        ? [{ key: "mp4", label: "Tải MP4", onClick: () => window.location.assign(detail.mp4!.download_url) }]
        : []),
      ...(detail.has_script
        ? [
            { key: "clone", label: "Nhân bản", onClick: () => setClone("same") },
            ...(detail.platform === "facebook"
              ? [{ key: "tiktok", label: "Tạo bản TikTok", onClick: () => setClone("tiktok") }]
              : []),
          ]
        : []),
      ...(mine
        ? [
            { type: "divider" as const },
            { key: "move", label: "Chuyển sang nhóm khác", disabled: detail.locked, onClick: () => setMoving(true) },
            { key: "delete", label: "Xóa video", danger: true, disabled: detail.locked, onClick: remove },
          ]
        : []),
    ];
  }
  const name = video.title || video.topic;
  return (
    <div
      onClick={(event) => {
        event.stopPropagation();
      }}
      onMouseDown={(event) => event.stopPropagation()}
    >
      {video.queue && (
        <Typography.Text
          type={video.queue.error ? "warning" : "secondary"}
          style={{ fontSize: 12 }}
          title={video.queue.error ?? undefined}
        >
          Hàng chờ: {video.queue.fanpage}
        </Typography.Text>
      )}
      <Flex gap={4} align="center">
        {video.post_stage === "ready" && video.suggested_post_at != null && (
          <ApproveVideoButton videoId={video.id} onDone={() => changed()} />
        )}
        <Dropdown
          trigger={["click"]}
          placement="bottomRight"
          onOpenChange={(next) => {
            // Read the full video once, when the menu is first opened; no per-row background requests.
            if (next && !detail) void read();
          }}
          menu={{ items: menuItems() }}
        >
          <Button size="small" type="text" icon={<MoreOutlined />} aria-label={`Thao tác với video ${name}`} />
        </Dropdown>
      </Flex>
      {detail && (
        <EditorContext.Provider
          value={{
            locked: detail.locked,
            readOnly: true,
            flush: async () => {},
            reportFailed: () => {},
            track: () => {},
            onSaved: (next) => void changed(next),
          }}
        >
          <FormDrawer title="Đăng bài và hàng chờ" open={open} onClose={() => setOpen(false)} footer={null}>
            <Flex vertical gap={12}>
              <Typography.Text strong>{name}</Typography.Text>
              {detail.mp4 && (
                <>
                  <PublishButton video={detail} />
                  {detail.post_stage === "ready" && detail.plan_idea?.suggested_post_at && (
                    <ApproveVideoButton
                      videoId={video.id}
                      onDone={() => {
                        void read();
                        return changed();
                      }}
                    />
                  )}
                  <QueueButton
                    video={detail}
                    onChanged={async () => {
                      await read();
                      await changed();
                    }}
                  />
                </>
              )}
              {(detail.active_job ?? detail.failed_job) && (
                <JobActions
                  job={{
                    ...(detail.active_job ?? detail.failed_job)!,
                    can_cancel:
                      detail.active_job?.status === "queued" ||
                      (detail.active_job?.status === "running" && detail.active_job.node_stage === "ready"),
                  }}
                  onDone={async () => {
                    await read();
                    await changed();
                  }}
                />
              )}
            </Flex>
          </FormDrawer>
          <CloneModal videoId={video.id} target={clone} onClose={() => setClone(null)} />
          <MoveGroupDrawer
            video={detail}
            open={moving}
            onClose={() => setMoving(false)}
            onMoved={(next) => {
              void changed(next);
            }}
          />
        </EditorContext.Provider>
      )}
    </div>
  );
}
