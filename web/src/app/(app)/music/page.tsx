"use client";

import { DeleteOutlined, EditOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Popconfirm, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRef, useState } from "react";
import TrackFilters from "@/components/music/TrackFilters";
import TrackModal, { MAX_MUSIC_BYTES, type TrackTarget } from "@/components/music/TrackModal";
import TrackTags from "@/components/music/TrackTags";
import { useTracks, type TrackFilters as Filters } from "@/components/music/useTracks";
import { api, errorMessage, formatDateTime, type MusicTrack } from "@/lib/api";
import PageHeader from "@/components/PageHeader";

export default function MusicPage() {
  const { message } = App.useApp();
  const input = useRef<HTMLInputElement>(null);
  const [filters, setFilters] = useState<Filters>({ q: "" });
  const [target, setTarget] = useState<TrackTarget | null>(null);
  const { tracks, loading, reload } = useTracks(filters);

  function chosen(file: File | undefined) {
    if (input.current) {
      input.current.value = "";
    }
    if (!file) {
      return;
    }
    if (file.size > MAX_MUSIC_BYTES) {
      message.error("File nhạc quá 20 MB, hãy chọn file nhỏ hơn");
      return;
    }
    setTarget({ file });
  }

  async function remove(track: MusicTrack) {
    try {
      await api(`/music/${track.id}`, "DELETE");
      message.success("Đã xoá bài nhạc");
    } catch (err) {
      message.error(errorMessage(err));
    }
    await reload();
  }

  const columns: ColumnsType<MusicTrack> = [
    {
      title: "Bài nhạc",
      key: "name",
      render: (_, track) => (
        <Flex vertical gap={6}>
          <Typography.Text strong>{track.name}</Typography.Text>
          <audio src={track.url} controls preload="none" style={{ width: 280 }} />
        </Flex>
      ),
    },
    { title: "Chủ đề và mood", key: "tags", width: 260, render: (_, track) => <TrackTags track={track} /> },
    {
      title: "Nguồn / giấy phép",
      key: "license",
      width: 220,
      render: (_, track) => track.license_note || <Typography.Text type="warning">Chưa ghi nguồn</Typography.Text>,
    },
    { title: "Người thêm", dataIndex: "created_by", width: 160 },
    { title: "Ngày thêm", key: "created", width: 150, render: (_, track) => formatDateTime(track.created_at) },
    {
      title: "Thao tác",
      key: "actions",
      width: 200,
      render: (_, track) => (
        <Space wrap>
          <Button icon={<EditOutlined />} onClick={() => setTarget({ track })}>
            Sửa
          </Button>
          <Popconfirm
            title="Xoá bài này khỏi thư viện?"
            description="Video đã dùng bài này vẫn giữ nhạc."
            okText="Xoá"
            cancelText="Huỷ"
            onConfirm={() => remove(track)}
          >
            <Button danger icon={<DeleteOutlined />}>
              Xoá
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <input
        ref={input}
        type="file"
        accept="audio/mpeg,.mp3"
        hidden
        aria-label="Chọn file MP3 cho thư viện"
        onChange={(event) => chosen(event.target.files?.[0])}
      />
      <PageHeader
        title="Thư viện nhạc"
        actions={
          <Button type="primary" icon={<UploadOutlined />} onClick={() => input.current?.click()}>
            Tải nhạc lên
          </Button>
        }
      >
        <TrackFilters value={filters} onChange={setFilters} />
      </PageHeader>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<MusicTrack>
          rowKey="id"
          columns={columns}
          dataSource={tracks}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 1150 }}
          locale={{ emptyText: "Chưa có bài nhạc nào" }}
        />
      </Card>
      <TrackModal
        target={target}
        onClose={() => setTarget(null)}
        onDone={async () => {
          message.success(target && "file" in target ? "Đã thêm vào thư viện" : "Đã lưu");
          setTarget(null);
          await reload();
        }}
      />
    </>
  );
}
