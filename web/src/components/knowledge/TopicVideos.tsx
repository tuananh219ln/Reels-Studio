"use client";

import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Empty, Flex, Input, Select, Table, Typography, theme } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type VideoRow } from "@/lib/api";
import VideoStatusTags from "@/components/VideoStatusTags";
import { PostedPlatforms, VideoKindTags } from "@/components/VideoKind";

/** Accents and case ignored, so "rau mam" finds "Rau mầm". */
function plain(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
}

/** "Video" in Kho kiến thức: the videos of one topic group, newest first, each opening its video page. */
export default function TopicVideos({ topicId, canCreate }: { topicId: number; canCreate: boolean }) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api<VideoRow[]>(`/videos?knowledge_topic_id=${topicId}`)
      .then(setRows)
      .catch((err) => {
        setRows([]);
        message.error(errorMessage(err));
      });
  }, [topicId, message]);

  const statuses = [...new Set((rows ?? []).map((row) => row.status_label))];
  const wanted = plain(search.trim());
  const shown = (rows ?? []).filter(
    (row) =>
      (!status || row.status_label === status) &&
      (!wanted || plain(row.title).includes(wanted) || plain(row.topic).includes(wanted)),
  );

  return (
    <Flex vertical gap={12} data-testid="topic-videos">
      <Flex wrap gap={8} justify="space-between">
        <Flex wrap gap={8}>
          <Input
            aria-label="Tìm video của nhóm"
            placeholder="Tìm theo tiêu đề hoặc chủ đề"
            prefix={<SearchOutlined />}
            allowClear
            style={{ width: 260 }}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Select
            aria-label="Trạng thái"
            placeholder="Mọi trạng thái"
            allowClear
            style={{ width: 180 }}
            value={status}
            onChange={(value) => setStatus(value ?? null)}
            options={statuses.map((label) => ({ value: label, label }))}
          />
        </Flex>
        {canCreate && (
          <Link prefetch={false} href={`/videos?group=${topicId}`}>
            <Button type="primary" icon={<PlusOutlined />}>
              Tạo video
            </Button>
          </Link>
        )}
      </Flex>
      <Table<VideoRow>
        size="small"
        rowKey="id"
        loading={rows === null}
        dataSource={shown}
        pagination={shown.length > 20 ? { pageSize: 20, showSizeChanger: false } : false}
        scroll={{ x: 760 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={rows?.length ? "Không có video nào khớp" : "Nhóm này chưa có video nào"}
            />
          ),
        }}
        columns={[
          {
            key: "thumbnail",
            width: 56,
            render: (_, row) =>
              row.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- the api serves the thumbnail; next/image adds nothing here
                <img
                  src={row.thumbnail_url}
                  alt=""
                  width={36}
                  height={64}
                  style={{ objectFit: "cover", borderRadius: token.borderRadiusSM, display: "block" }}
                />
              ) : (
                <div
                  style={{
                    width: 36,
                    height: 64,
                    borderRadius: token.borderRadiusSM,
                    background: token.colorFillTertiary,
                  }}
                />
              ),
          },
          {
            key: "title",
            title: "Video",
            render: (_, row) => (
              <Flex vertical style={{ minWidth: 0 }}>
                <Link prefetch={false} href={`/videos/${row.id}`}>
                  <Typography.Text strong ellipsis style={{ color: "inherit", maxWidth: 300 }}>
                    {row.title || row.topic}
                  </Typography.Text>
                </Link>
                <Typography.Text type="secondary" ellipsis style={{ fontSize: 13, maxWidth: 300 }}>
                  {row.topic}
                  {row.plan_day ? `, kế hoạch ngày ${row.plan_day}` : ""}
                </Typography.Text>
              </Flex>
            ),
          },
          {
            key: "kind",
            title: "Loại",
            width: 170,
            render: (_, row) => <VideoKindTags video={row} />,
          },
          {
            key: "status",
            title: "Trạng thái",
            width: 110,
            render: (_, row) => <VideoStatusTags video={row} only="status" />,
          },
          {
            key: "platforms",
            title: "Đã đăng",
            width: 110,
            render: (_, row) => <PostedPlatforms postedOn={row.posted_on} />,
          },
          {
            key: "made",
            title: "Tạo",
            width: 150,
            render: (_, row) => (
              <Flex vertical>
                <Typography.Text ellipsis>{row.created_by}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {formatDateTime(row.created_at)}
                </Typography.Text>
              </Flex>
            ),
          },
        ]}
      />
    </Flex>
  );
}
