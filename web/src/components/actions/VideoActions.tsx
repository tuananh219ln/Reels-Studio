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
import { App, Button, Flex, Spin, Typography } from "antd";
import Link from "next/link";
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
        <Button
          size="small"
          type="text"
          icon={<MoreOutlined />}
          aria-label={`Thao tác với video ${name}`}
          onClick={(event) => {
            event.preventDefault();
            setDetail(null);
            setOpen(true);
            void read();
          }}
        />
      </Flex>
      <FormDrawer title="Thao tác video" open={open} onClose={() => setOpen(false)} footer={null}>
        {!detail ? (
          failed ? (
            <Button onClick={() => void read()}>Thử lại</Button>
          ) : (
            <Spin />
          )
        ) : (
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
            <Flex vertical gap={12}>
              <Typography.Text strong>{name}</Typography.Text>
              <Link href={`/videos/${video.id}`} prefetch={false}>
                Mở video
              </Link>
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
                  <Button href={detail.mp4.download_url}>Tải MP4</Button>
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
              {detail.has_script && (
                <>
                  <Button onClick={() => setClone("same")}>Nhân bản</Button>
                  {detail.platform === "facebook" && <Button onClick={() => setClone("tiktok")}>Tạo bản TikTok</Button>}
                </>
              )}
              {detail.created_by_id === me.id && (
                <>
                  <Button disabled={detail.locked} onClick={() => setMoving(true)}>
                    Chuyển sang nhóm khác
                  </Button>
                  <Button danger disabled={detail.locked} onClick={remove}>
                    Xóa video
                  </Button>
                </>
              )}
            </Flex>
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
      </FormDrawer>
    </div>
  );
}
