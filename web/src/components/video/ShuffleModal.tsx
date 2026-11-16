"use client";
import FormDrawer from "@/components/FormDrawer";
import { api, errorMessage } from "@/lib/api";
import { ReloadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Checkbox, Flex, InputNumber, Spin, Typography } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

/** What the api offers for "Nhân bản xáo cảnh" (api shuffle.preview): the orders "Tạo N bản" makes, as scene ids. */
type Preview = {
  free_scenes: number;
  max_distinct: number;
  orders: number[][];
  scenes: { id: number; number: number; name: string }[];
  numbered: boolean;
  warnings: string[];
};

type Made = { videos: { id: number; name: string }[]; renumbered: boolean; warnings: string[] };

const MAX_COPIES = 20;

/** "Nhân bản xáo cảnh": N copies of the video, each with its content scenes in another order (the title scene stays
 * first) and their list numbers written for their new place. No AI call; each copy is rendered before posting. */
export default function ShuffleModal({
  videoId,
  open,
  onClose,
  onCreated,
}: {
  videoId: number;
  open: boolean;
  onClose: () => void;
  onCreated?: () => void | Promise<void>;
}) {
  const { message, notification } = App.useApp();
  const router = useRouter();
  const [count, setCount] = useState(1);
  const [lockLast, setLockLast] = useState(false);
  const [renumber, setRenumber] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  // Only the newest preview is shown, when an older request answers late.
  const asked = useRef(0);

  const load = useCallback(async () => {
    const ask = ++asked.current;
    setLoading(true);
    try {
      const next = await api<Preview>(`/shuffle/videos/${videoId}/preview`, "POST", { count, lock_last: lockLast });
      if (ask === asked.current) setPreview(next);
    } catch (err) {
      if (ask === asked.current) message.error(errorMessage(err));
    } finally {
      if (ask === asked.current) setLoading(false);
    }
  }, [videoId, count, lockLast, message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the preview follows the dialog's choices
    if (open) void load();
  }, [open, load]);

  const orders = preview?.orders ?? [];
  const names = new Map(preview?.scenes.map((scene) => [scene.id, scene]) ?? []);
  const tooFew = preview !== null && preview.free_scenes < 2;

  async function submit() {
    setBusy(true);
    try {
      const made = await api<Made>(`/shuffle/videos/${videoId}/copies`, "POST", {
        orders,
        lock_last: lockLast,
        renumber,
      });
      onClose();
      await onCreated?.();
      if (made.videos.length === 1) {
        message.success("Đã tạo 1 bản. Nhớ đổi tiêu đề để tránh trùng lặp, rồi render lại MP4 trước khi đăng");
        router.push(`/videos/${made.videos[0].id}`);
      } else {
        notification.success({
          title: `Đã tạo ${made.videos.length} bản`,
          description: (
            <Flex vertical gap={4}>
              <span>Nhớ đổi tiêu đề cho từng bản để tránh trùng lặp, rồi render lại MP4 trước khi đăng.</span>
              {made.videos.map((video) => (
                <Link key={video.id} prefetch={false} href={`/videos/${video.id}`}>
                  {video.name}
                </Link>
              ))}
            </Flex>
          ),
          duration: 0,
        });
      }
      for (const warning of made.warnings) message.warning(warning);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Nhân bản xáo cảnh"
      open={open}
      onClose={onClose}
      onOk={submit}
      okText={`Tạo ${orders.length || count} bản`}
      okButtonProps={{ disabled: loading || tooFew || orders.length === 0 }}
      confirmLoading={busy}
      destroyOnHidden
      width={560}
    >
      <Flex vertical gap={12}>
        <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
          Mỗi bản giữ nguyên nội dung, ảnh, nhạc của video này nhưng đổi thứ tự các cảnh nội dung; cảnh tiêu đề luôn
          đứng đầu. Không gọi AI. Bản sao chưa có MP4, cần render trước khi đăng.
        </Typography.Paragraph>
        {tooFew ? (
          <Alert type="info" showIcon title="Cần ít nhất 2 cảnh xáo được" />
        ) : (
          <>
            <Flex align="center" gap={8} wrap>
              <Typography.Text>Số bản</Typography.Text>
              <InputNumber
                aria-label="Số bản"
                min={1}
                max={Math.max(1, Math.min(MAX_COPIES, preview?.max_distinct ?? MAX_COPIES))}
                precision={0}
                value={count}
                onChange={(value) => setCount(Math.max(1, Math.min(MAX_COPIES, value ?? 1)))}
              />
              {preview && (
                <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                  Tối đa {preview.max_distinct} bản khác nhau
                </Typography.Text>
              )}
            </Flex>
            <Checkbox checked={lockLast} onChange={(event) => setLockLast(event.target.checked)}>
              Giữ cố định cảnh cuối (cảnh kết, kêu gọi hành động)
            </Checkbox>
            <Checkbox
              checked={renumber && Boolean(preview?.numbered)}
              disabled={!preview?.numbered}
              onChange={(event) => setRenumber(event.target.checked)}
            >
              Đánh lại số thứ tự ở đầu chữ và lời đọc
              {preview && !preview.numbered && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {" "}
                  (không phát hiện đánh số, giữ nguyên chữ)
                </Typography.Text>
              )}
            </Checkbox>
            <Flex justify="space-between" align="center">
              <Typography.Text strong>Xem trước</Typography.Text>
              <Button size="small" icon={<ReloadOutlined />} disabled={loading} onClick={() => void load()}>
                Xáo lại
              </Button>
            </Flex>
            <Spin spinning={loading}>
              <Flex vertical gap={8} data-testid="shuffle-preview">
                {orders.map((order, index) => (
                  <div key={order.join(",")}>
                    <Typography.Text>
                      Bản {index + 1}: {order.map((sceneId) => names.get(sceneId)?.number ?? "?").join(" → ")}
                    </Typography.Text>
                    <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: 0, fontSize: 12 }}>
                      {order.map((sceneId) => names.get(sceneId)?.name || "(chưa có chữ)").join(" · ")}
                    </Typography.Paragraph>
                  </div>
                ))}
              </Flex>
            </Spin>
            {preview?.warnings.map((warning) => (
              <Alert key={warning} type="warning" showIcon title={warning} />
            ))}
          </>
        )}
      </Flex>
    </FormDrawer>
  );
}
