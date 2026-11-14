"use client";

import { UnorderedListOutlined } from "@ant-design/icons";
import { Alert, App, Button, Checkbox, Flex, Popconfirm, Select, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, type QueueItem, type VideoDetail } from "@/lib/api";
import { useMe } from "@/components/MeContext";
import { myPages, pageOptions } from "@/lib/myPages";
import { loadLastChoices, myPageOfGroup, saveLastChoice } from "@/lib/lastChoices";
import FormDrawer from "@/components/FormDrawer";

const OWN_PAGE = 0;

/** "Thêm vào hàng chờ" beside "Đăng": once a member has watched the MP4, it waits for its Page's next free posting
 * time, and the worker schedules it there. By default it goes to the member's own Page of the video's topic group. */
export default function QueueButton({
  video,
  onChanged,
}: {
  video: VideoDetail;
  onChanged?: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const { me } = useMe();
  const [item, setItem] = useState<QueueItem | null>(null);
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<number>(OWN_PAGE);
  const [autoComment, setAutoComment] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<{ item: QueueItem | null }>(`/queue/videos/${video.id}`).then(
      (answer) => setItem(answer.item),
      () => undefined,
    );
  }, [video.id]);
  // A post the worker made from the queue shows up on the video as it is reloaded; read the queue again with it.
  useEffect(load, [load, video.publications.length]);

  // "Page của tôi" while the member has a Page of the video's group; without one, the Page they last chose (B3).
  function openDrawer() {
    setOpen(true);
    if (myPageOfGroup(video, me.id) === null) {
      loadLastChoices().then((last) => {
        if (myPages(video.fanpages, me.id).some((row) => row.id === last.fanpage_id)) {
          setPage(last.fanpage_id as number);
        }
      });
    }
  }

  async function add() {
    setBusy(true);
    try {
      const answer = await api<{ item: QueueItem }>("/queue", "POST", {
        video_id: video.id,
        fanpage_id: page === OWN_PAGE ? null : page,
        auto_comment: autoComment,
      });
      if (page !== OWN_PAGE) await saveLastChoice({ fanpage_id: page });
      setItem(answer.item);
      setOpen(false);
      await onChanged?.();
      message.success(`Đã thêm vào hàng chờ của “${answer.item.fanpage}”`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(queued: QueueItem) {
    try {
      await api(`/queue/items/${queued.id}`, "DELETE");
      setItem(null);
      await onChanged?.();
    } catch (err) {
      message.error(errorMessage(err));
      load();
    }
  }

  if (item) {
    return (
      <Flex align="center" gap={8} wrap data-testid="video-queue">
        <Typography.Text>
          Trong hàng chờ của{" "}
          <Link prefetch={false} href="/fanpages">
            “{item.fanpage}”
          </Link>
        </Typography.Text>
        {item.error && <Typography.Text type="warning">{item.error}</Typography.Text>}
        <Popconfirm title="Bỏ video khỏi hàng chờ?" okText="Bỏ" cancelText="Không" onConfirm={() => remove(item)}>
          <Button size="small">Bỏ khỏi hàng chờ</Button>
        </Popconfirm>
      </Flex>
    );
  }
  return (
    <>
      <Button icon={<UnorderedListOutlined />} disabled={video.locked || video.mp4_outdated} onClick={openDrawer}>
        Thêm vào hàng chờ
      </Button>
      <FormDrawer
        title="Thêm vào hàng chờ"
        open={open}
        onClose={() => setOpen(false)}
        okText="Thêm vào hàng chờ"
        cancelText="Huỷ"
        onOk={add}
        confirmLoading={busy}
      >
        <Flex vertical gap={8}>
          <Alert
            type="info"
            showIcon
            title="Hãy xem hết MP4 trước khi thêm. Video sẽ tự lên lịch vào khung giờ trống gần nhất của Page."
          />
          <Select
            aria-label="Fanpage"
            value={page}
            onChange={setPage}
            style={{ maxWidth: 360 }}
            options={[
              {
                value: OWN_PAGE,
                label: video.knowledge_topic
                  ? `Page của tôi cho nhóm “${video.knowledge_topic}”`
                  : "Page của tôi cùng nhóm chủ đề",
              },
              ...pageOptions(video.fanpages, me.id),
            ]}
          />
          <Checkbox checked={autoComment} onChange={(event) => setAutoComment(event.target.checked)}>
            Tự bình luận khi bài lên (bình luận ghim kèm link sản phẩm Shopee đã chọn)
          </Checkbox>
          <Typography.Text type="secondary">
            Khung giờ của mỗi Page đặt ở{" "}
            <Link prefetch={false} href="/fanpages">
              Quản lý kênh
            </Link>
            .
          </Typography.Text>
        </Flex>
      </FormDrawer>
    </>
  );
}
