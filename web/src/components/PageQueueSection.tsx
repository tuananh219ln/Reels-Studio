"use client";

import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined } from "@ant-design/icons";
import { App, Button, Divider, Flex, Popconfirm, Select, Spin, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, formatDateTime, type QueueOverview, type QueuePage } from "@/lib/api";
import VideoThumbnail from "@/components/VideoThumbnail";

const TIME = /^([01]?\d|2[0-3]):[0-5]\d$/;

/** The part of a Page's card on "Quản lý Page" about posting: its topic group and posting times (its owner changes
 * them), the free times ahead, and its queue of videos, which the worker schedules one by one at those times. */
export default function PageQueueSection({
  page,
  overview,
  onChanged,
}: {
  page: QueuePage;
  overview: QueueOverview;
  onChanged: (overview: QueueOverview) => void;
}) {
  const { message } = App.useApp();
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
    void run(`/queue/pages/${page.id}`, "PATCH", { post_times: times.length ? times : null });
  }

  return (
    <Spin spinning={busy}>
      <Flex vertical gap={8} data-testid="page-queue">
        <Divider plain style={{ margin: "2px 0" }} titlePlacement="start">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Đăng theo lịch
          </Typography.Text>
        </Divider>
        {page.mine ? (
          <Flex vertical gap={6}>
            <Select
              size="small"
              aria-label={`Nhóm chủ đề của ${page.name}`}
              placeholder="Chọn nhóm chủ đề Page đăng"
              value={page.topic?.id ?? null}
              allowClear
              onChange={(value) => run(`/queue/pages/${page.id}`, "PATCH", { knowledge_topic_id: value ?? null })}
              options={overview.topics.map((topic) => ({ value: topic.id, label: topic.name }))}
            />
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
          </Flex>
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {page.topic ? `Nhóm “${page.topic.name}”` : "Chưa gắn nhóm chủ đề"}
            {page.post_times.length > 0 && `, đăng lúc ${page.post_times.join(", ")}`}
          </Typography.Text>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {page.post_times.length === 0
            ? "Chưa có giờ đăng: hãy gắn nhóm chủ đề hoặc nhập giờ riêng."
            : page.own_times
              ? "Giờ riêng của Page (giờ Việt Nam)."
              : "Theo giờ đăng của nhóm chủ đề (giờ Việt Nam)."}
          {page.post_times.length > 0 &&
            (page.free_slots.length > 0
              ? ` Khung trống trong ${overview.fill_ahead_hours} giờ tới: ${page.free_slots.map(formatDateTime).join(", ")}.`
              : ` Không còn khung trống trong ${overview.fill_ahead_hours} giờ tới.`)}
        </Typography.Text>
        {page.items.length === 0 ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Hàng chờ trống. Thêm video từ trang video, nút “Thêm vào hàng chờ”.
          </Typography.Text>
        ) : (
          <Flex vertical gap={6}>
            <Typography.Text style={{ fontSize: 12 }}>Hàng chờ ({page.items.length})</Typography.Text>
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
