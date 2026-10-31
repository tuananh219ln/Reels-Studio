"use client";

import { App, Card, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type PostRow } from "@/lib/api";
import { POST_STATUS } from "@/lib/postStatus";

/** The reels posted or scheduled from their video page, latest time first. */
export default function PostsPage() {
  const { message } = App.useApp();
  const [posts, setPosts] = useState<PostRow[]>([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Bài đăng
      </Typography.Title>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<PostRow>
          rowKey="video_id"
          columns={columns}
          dataSource={posts}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 900 }}
          locale={{ emptyText: "Chưa có video nào đã đăng hoặc hẹn lịch" }}
        />
      </Card>
    </>
  );
}
