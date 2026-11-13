"use client";

import { App, Alert, Button, Card, Checkbox, Flex, Space, Table, Tag, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { usePolling } from "@/lib/polling";

type Progress = { stage?: string; replaced?: number[]; kept?: number[]; render_after?: boolean };
type Row = {
  id: number;
  topic: string;
  eligible: boolean;
  reason: string | null;
  job: { id: number; status: string; error: string | null; progress: Progress } | null;
};
type Payload = { videos: Row[]; limit: number; batch_limit: number };

export default function ReworkVideos() {
  const { message, modal } = App.useApp();
  const [data, setData] = useState<Payload | null>(null);
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [replaceManual, setReplaceManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const result = await api<Payload>("/rework/videos");
      setData(result);
      setError("");
      setSelected((old) => old.filter((id) => result.videos.some((row) => row.id === id && row.eligible)));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);
  useEffect(() => {
    let alive = true;
    void api<Payload>("/rework/videos")
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((err) => {
        if (alive) setError(errorMessage(err));
      });
    return () => {
      alive = false;
    };
  }, []);
  const running = data?.videos.some(
    (row) => row.job?.status === "queued" || row.job?.status === "running" || row.reason?.includes("job"),
  );
  usePolling(load, running ? 5000 : 60_000);
  const limit = data?.batch_limit ?? 50;

  function confirm() {
    modal.confirm({
      title: `Nâng cấp ${selected.length} video đã chọn?`,
      content: (
        <Flex vertical gap={8}>
          <Typography.Text>
            Giữ ý chính và thứ tự cảnh, rút gọn lời đọc, tìm tư liệu rồi xếp render lại. Có phí AI chọn tư liệu và tạo
            giọng đọc.
          </Typography.Text>
          <Typography.Text>
            {replaceManual
              ? "Thay cả ảnh/clip đã chọn tay khi tìm được tư liệu mới."
              : "Giữ ảnh/clip đã chọn tay; làm lại tư liệu tự chọn và cảnh còn thiếu."}
          </Typography.Text>
          <Typography.Text>
            Video sẽ được rút khỏi hàng chờ đăng. Sau khi render, cần xem lại và duyệt đăng; không tự đăng.
          </Typography.Text>
        </Flex>
      ),
      okText: "Nâng cấp và render lại",
      cancelText: "Hủy",
      async onOk() {
        setBusy(true);
        try {
          const result = await api<{ queued: number }>("/rework/videos", "POST", {
            ids: selected,
            replace_manual: replaceManual,
            render_after: true,
          });
          message.success(`Đã xếp nâng cấp ${result.queued} video`);
          setSelected([]);
          await load();
        } catch (err) {
          message.error(errorMessage(err));
          throw err;
        } finally {
          setBusy(false);
        }
      },
    });
  }

  return (
    <Flex vertical gap={20}>
      <div>
        <Typography.Title level={2}>Nâng cấp video chưa đăng</Typography.Title>
        <Typography.Paragraph type="secondary">
          Chỉnh kịch bản để tìm clip thật, tự chọn tư liệu và render lại. Chỉ xử lý video do bạn tạo; video đã đăng hoặc
          lên lịch được giữ nguyên.
        </Typography.Paragraph>
      </div>
      {error && <Alert type="error" title={error} showIcon />}
      <Alert
        type="info"
        showIcon
        title="Không cần tìm link thủ công"
        description="App tự tìm clip rồi dùng ảnh khi không có đoạn phù hợp. Nếu không tìm được tư liệu mới, giữ tư liệu cũ và báo trong kết quả. Video đã lên lịch cần hủy lịch cũ trước khi nâng cấp."
      />
      <Card>
        <Flex vertical gap={16}>
          <Checkbox
            checked={replaceManual}
            onChange={(event) => setReplaceManual(event.target.checked)}
            disabled={busy}
          >
            Thay cả ảnh/clip đã chọn tay
          </Checkbox>
          <Space wrap>
            <Button
              disabled={busy || !data?.videos.some((row) => row.eligible)}
              onClick={() =>
                setSelected(
                  data?.videos
                    .filter((row) => row.eligible)
                    .slice(0, limit)
                    .map((row) => row.id) ?? [],
                )
              }
            >
              Chọn video đủ điều kiện
            </Button>
            <Button type="primary" loading={busy} disabled={!selected.length} onClick={confirm}>
              Nâng cấp {selected.length ? `(${selected.length})` : "video đã chọn"}
            </Button>
            <Typography.Text type="secondary">
              Tối đa {limit} video mỗi lượt · {selected.length} video đã chọn
            </Typography.Text>
          </Space>
          <Table<Row>
            rowKey="id"
            dataSource={data?.videos ?? []}
            loading={!data && !error}
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setSelected(keys.slice(0, limit)),
              getCheckboxProps: (row) => ({ disabled: !row.eligible || busy }),
            }}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 700 }}
            columns={[
              {
                title: "Video",
                key: "topic",
                render: (_, row) => (
                  <Link prefetch={false} href={`/videos/${row.id}`}>
                    #{row.id} · {row.topic}
                  </Link>
                ),
              },
              {
                title: "Điều kiện",
                key: "eligible",
                render: (_, row) =>
                  row.eligible ? (
                    <Tag color="green">Có thể nâng cấp</Tag>
                  ) : (
                    <Typography.Text type="secondary">{row.reason}</Typography.Text>
                  ),
              },
              {
                title: "Lần nâng cấp gần nhất",
                key: "job",
                render: (_, row) => {
                  if (!row.job) return "—";
                  if (row.job.status === "failed")
                    return <Typography.Text type="danger">{row.job.error}</Typography.Text>;
                  if (row.job.status === "cancelled") return <Tag>Đã hủy</Tag>;
                  if (row.job.status !== "done") return <Tag color="processing">Đang xử lý</Tag>;
                  return (
                    <Flex vertical gap={4}>
                      <Typography.Text>
                        Đã đổi {row.job.progress.replaced?.length ?? 0} cảnh · Giữ tư liệu cũ{" "}
                        {row.job.progress.kept?.length ?? 0} cảnh
                      </Typography.Text>
                      <Link prefetch={false} href={`/videos/${row.id}`}>
                        Xem video và trạng thái render
                      </Link>
                    </Flex>
                  );
                },
              },
            ]}
          />
        </Flex>
      </Card>
      {data && data.videos.length >= data.limit && (
        <Typography.Text type="secondary">Đang hiển thị {data.limit} video gần nhất.</Typography.Text>
      )}
    </Flex>
  );
}
