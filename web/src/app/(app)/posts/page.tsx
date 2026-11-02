"use client";

import { CalendarOutlined } from "@ant-design/icons";
import { App, Button, Card, Segmented, Select, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";
import PageHeader from "@/components/PageHeader";

/** The reels posted or scheduled from their video page, latest time first. */
export default function PostsPage() {
  const { message } = App.useApp();
  const [posts, setPosts] = useState<PostRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<PostRow["status"] | "all">("all");
  const [fanpage, setFanpage] = useState<string | null>(null);

  useEffect(() => {
    api<PostRow[]>("/posts")
      .then(setPosts)
      .catch((err) => message.error(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [message]);

  const columns: ColumnsType<PostRow> = [
    {
      title: "Video",
      key: "video",
      render: (_, post) => <Link href={`/videos/${post.video_id}`}>{post.title}</Link>,
    },
    { title: "Fanpage", key: "fanpage", width: 220, render: (_, post) => post.fanpage ?? "—" },
    {
      title: "Trạng thái",
      key: "status",
      width: 130,
      render: (_, post) => <Tag color={POST_STATUS[post.status].color}>{POST_STATUS[post.status].label}</Tag>,
    },
    { title: "Giờ đăng", key: "at", width: 150, render: (_, post) => formatDateTime(post.at) },
    { title: "Người đăng", dataIndex: "created_by", width: 170 },
    {
      title: "",
      key: "reel",
      width: 100,
      render: (_, post) =>
        post.url && (
          <a href={post.url} target="_blank" rel="noreferrer">
            Xem Reel
          </a>
        ),
    },
  ];

  const pages = [...new Set(posts.map((post) => post.fanpage).filter((name): name is string => Boolean(name)))];
  const shown = posts.filter(
    (post) => (status === "all" || post.status === status) && (fanpage === null || post.fanpage === fanpage),
  );
  const count = (which: PostRow["status"]) => posts.filter((post) => post.status === which).length;

  return (
    <>
      <PageHeader
        title="Bài đăng"
        description={
          posts.length > 0 &&
          `${count("scheduled")} bài đã hẹn lịch · ${count("published")} bài đã đăng, giờ mới nhất trước.`
        }
        actions={
          <Link href="/calendar">
            <Button icon={<CalendarOutlined />}>Xem dạng lịch</Button>
          </Link>
        }
      >
        <Segmented
          aria-label="Lọc theo trạng thái"
          value={status}
          onChange={(value) => setStatus(value as PostRow["status"] | "all")}
          options={[
            { value: "all", label: "Tất cả" },
            { value: "scheduled", label: POST_STATUS.scheduled.label },
            { value: "published", label: POST_STATUS.published.label },
          ]}
        />
        {pages.length > 1 && (
          <Select
            aria-label="Lọc theo Fanpage"
            allowClear
            placeholder="Mọi Fanpage"
            value={fanpage}
            onChange={(value) => setFanpage(value ?? null)}
            options={pages.map((name) => ({ value: name, label: name }))}
            style={{ width: 220 }}
          />
        )}
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<PostRow>
          rowKey="video_id"
          columns={columns}
          dataSource={shown}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 900 }}
          locale={{ emptyText: "Chưa có video nào đã đăng hoặc hẹn lịch" }}
        />
      </Card>
    </>
  );
}
