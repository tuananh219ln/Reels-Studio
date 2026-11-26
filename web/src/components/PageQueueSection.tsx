"use client";
import VideoActions from "@/components/actions/VideoActions";

import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined } from "@ant-design/icons";
import { App, Button, Flex, Popconfirm, Select, Spin, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, formatDateTime, type QueueOverview, type QueuePage } from "@/lib/api";
import VideoThumbnail from "@/components/VideoThumbnail";
import ScheduleZonePicker from "@/components/ScheduleZonePicker";
import { timeWithZone, VN_ZONE, zoneName } from "@/lib/scheduleZone";

const TIME = /^([01]?\d|2[0-3]):[0-5]\d$/;
// The next few free times are enough to see when the queue will post; the rest is a count.
const SHOWN_SLOTS = 3;

/** "Đăng theo lịch" on a Page's "Lịch đăng" tab: its topic group and posting times (its owner changes them), the free
 * times ahead, and its queue of videos, which the worker schedules one by one at those times. */
export default function PageQueueSection({
  page,
  overview,
  onChanged,
}: {
  page: QueuePage;
  overview: QueueOverview;
  onChanged: (overview: QueueOverview) => void;
}) {
  const { message, modal } = App.useApp();
  const [busy, setBusy] = useState(false);

  async function run(path: string, method: "PATCH" | "POST" | "DELETE", body?: object) {
    setBusy(true);
    try {
      onChanged(await api<QueueOverview>(path, method, body));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function move(index: number, by: number) {
    const ids = page.items.map((item) => item.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    void run(`/queue/pages/${page.id}/order`, "POST", { ids });
  }

  function setTimes(times: string[]) {
    const bad = times.find((value) => !TIME.test(value.trim()));
    if (bad) {
      message.error(`Giờ đăng “${bad}” phải có dạng HH:MM`);
      return;
    }
    // Without times of its own the Page follows its group, zone included.
    void run(
      `/queue/pages/${page.id}`,
      "PATCH",
      times.length ? { post_times: times } : { post_times: null, schedule_timezone: null },
    );
  }

  const zone = page.schedule_timezone;

  return (
    <Spin spinning={busy}>
      <Flex vertical gap={8} data-testid="page-queue">
        {page.mine ? (
          <Flex vertical gap={6}>
            <Typography.Text style={{ fontSize: 12 }}>Nhóm chủ đề Page đăng</Typography.Text>
            <Select
              size="small"
              aria-label={`Nhóm chủ đề của ${page.name}`}
              placeholder="Chọn nhóm chủ đề Page đăng"
              value={page.topic?.id ?? null}
              allowClear
              onChange={(value) => run(`/queue/pages/${page.id}`, "PATCH", { knowledge_topic_id: value ?? null })}
              options={overview.topics.map((topic) => ({ value: topic.id, label: topic.name }))}
            />
            <Typography.Text style={{ fontSize: 12 }}>Giờ đăng mỗi ngày ({zoneName(zone)})</Typography.Text>
            <Flex gap={6} align="center">
              <Select
                size="small"
                mode="tags"
                aria-label={`Giờ đăng của ${page.name}`}
                placeholder="Giờ đăng, ví dụ 20:00"
                value={page.post_times}
                style={{ flex: 1, minWidth: 0 }}
                tokenSeparators={[",", " "]}
                onChange={setTimes}
                options={page.post_times.map((value) => ({ value, label: value }))}
              />
              {page.own_times && page.topic && (
                <Button size="small" onClick={() => setTimes([])}>
                  Dùng giờ của nhóm
                </Button>
              )}
            </Flex>
            {page.own_times ? (
              <ScheduleZonePicker
                label={page.name}
                value={zone}
                onChange={(next) => {
                  if (next === zone) return;
                  // Two ways to change a zone; only the buttons answer, so Esc or the X never picks one.
                  modal.confirm({
                    title: `Đổi sang ${zoneName(next)}`,
                    content: `Giờ đăng ${page.post_times.join(", ")} đang theo ${zoneName(zone)}. Quy đổi để giữ đúng thời điểm cũ, hay giữ nguyên số giờ và đọc theo múi mới? Bài đã hẹn giờ không đổi.`,
                    okText: "Quy đổi",
                    cancelText: "Giữ số giờ",
                    closable: false,
                    maskClosable: false,
                    keyboard: false,
                    onOk: () =>
                      run(`/queue/pages/${page.id}`, "PATCH", { schedule_timezone: next, convert_times: true }),
                    onCancel: () => run(`/queue/pages/${page.id}`, "PATCH", { schedule_timezone: next }),
                  });
                }}
              />
            ) : (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Múi giờ theo nhóm chủ đề; nhập giờ riêng để chọn múi giờ riêng cho Page.
              </Typography.Text>
            )}
          </Flex>
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {page.topic ? `Nhóm “${page.topic.name}”` : "Chưa gắn nhóm chủ đề"}
            {page.post_times.length > 0 && `, đăng lúc ${page.post_times.join(", ")} (${zoneName(zone)})`}
          </Typography.Text>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {page.post_times.length === 0
            ? "Chưa có giờ đăng: hãy gắn nhóm chủ đề hoặc nhập giờ riêng."
            : page.own_times
              ? `Giờ riêng của Page (${zoneName(zone)}).`
              : `Theo giờ đăng của nhóm chủ đề (${zoneName(zone)}).`}
          {page.post_times.length > 0 &&
            (page.free_slots.length > 0
              ? ` Khung trống trong ${overview.fill_ahead_hours} giờ tới: ${page.free_slots
                  .slice(0, SHOWN_SLOTS)
                  .map((at) =>
                    zone === VN_ZONE ? formatDateTime(at) : `${formatDateTime(at)} (${timeWithZone(at, zone)})`,
                  )
                  .join(
                    ", ",
                  )}${page.free_slots.length > SHOWN_SLOTS ? ` và ${page.free_slots.length - SHOWN_SLOTS} khung khác` : ""}.`
              : ` Không còn khung trống trong ${overview.fill_ahead_hours} giờ tới.`)}
        </Typography.Text>
        <Typography.Text strong style={{ fontSize: 13, marginTop: 4 }}>
          Hàng chờ ({page.items.length})
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Video chờ đến lượt đăng, theo thứ tự dưới đây. Khi một khung giờ trống còn trong {overview.fill_ahead_hours}{" "}
          giờ tới, video đầu hàng được hẹn giờ vào khung đó và chuyển sang “Đã hẹn giờ”.
        </Typography.Text>
        {page.items.length === 0 ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Hàng chờ trống. Thêm video từ trang video, nút “Thêm vào hàng chờ”.
          </Typography.Text>
        ) : (
          <Flex vertical gap={6}>
            {page.items.map((item, index) => (
              <Flex key={item.id} gap={8} align="center" data-testid="queue-item">
                <Typography.Text type="secondary" style={{ width: 16, fontSize: 12 }}>
                  {index + 1}
                </Typography.Text>
                <VideoThumbnail name={item.video.title} url={item.video.thumbnail_url} width={28} />
                <Flex vertical style={{ minWidth: 0, flex: 1 }}>
                  <Typography.Text ellipsis style={{ fontSize: 13 }}>
                    <Link prefetch={false} href={`/videos/${item.video.id}`}>
                      {item.video.title}
                    </Link>
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                    {item.added_by}, {formatDateTime(item.added_at)}
                  </Typography.Text>
                  {item.error && (
                    <Typography.Text type="warning" style={{ fontSize: 12 }}>
                      Chưa lên lịch được: {item.error}
                    </Typography.Text>
                  )}
                </Flex>
                <VideoActions
                  video={{ ...item.video, topic: item.video.title }}
                  onChanged={async () => onChanged(await api<QueueOverview>("/queue"))}
                />
                {page.mine && (
                  <>
                    <Button
                      size="small"
                      type="text"
                      aria-label="Lên"
                      icon={<ArrowUpOutlined />}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    />
                    <Button
                      size="small"
                      type="text"
                      aria-label="Xuống"
                      icon={<ArrowDownOutlined />}
                      disabled={index === page.items.length - 1}
                      onClick={() => move(index, 1)}
                    />
                  </>
                )}
                <Popconfirm
                  title="Bỏ video khỏi hàng chờ?"
                  okText="Bỏ"
                  cancelText="Không"
                  onConfirm={() => run(`/queue/items/${item.id}`, "DELETE")}
                >
                  <Button size="small" type="text" aria-label="Bỏ khỏi hàng chờ" icon={<DeleteOutlined />} />
                </Popconfirm>
              </Flex>
            ))}
          </Flex>
        )}
      </Flex>
    </Spin>
  );
}
