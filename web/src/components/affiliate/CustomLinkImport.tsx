"use client";
import { errorMessage, upload } from "@/lib/api";
import { UploadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Modal, Table, Tag, Tooltip, Typography, Upload } from "antd";
import { useState } from "react";

type Row = {
  row: number;
  original: string;
  link: string | null;
  state: "ok" | "others" | "error";
  message: string;
  name?: string;
};
type Result = { rows: Row[]; ok: number; others: number; errors: number; linked?: number };

const STATE: Record<Row["state"], { label: string; color: string }> = {
  ok: { label: "Sẽ gắn link", color: "green" },
  others: { label: "Của đồng đội", color: "gold" },
  error: { label: "Lỗi", color: "red" },
};

/** "Nhập link đã chuyển đổi": the Excel Shopee's Custom Link page gives back, previewed before anything is written
 * (docs/decisions/2026-11-24-custom-link-excel.md). */
export default function CustomLinkImport({ topicId, onDone }: { topicId?: number; onDone: () => void }) {
  const { message } = App.useApp();
  const [opened, setOpened] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);

  function close() {
    setOpened(false);
    setFile(null);
    setPreview(null);
  }

  async function choose(chosen: File) {
    setFile(chosen);
    setPreview(null);
    setBusy(true);
    try {
      setPreview(
        await upload<Result>("/affiliate-products/custom-link/import/preview", chosen, {
          knowledge_topic_id: String(topicId),
        }),
      );
    } catch (err) {
      message.error(errorMessage(err));
      setFile(null);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!file) {
      return;
    }
    setBusy(true);
    try {
      const done = await upload<Result>("/affiliate-products/custom-link/import", file, {
        knowledge_topic_id: String(topicId),
      });
      message.success(`Đã gắn link cho ${done.linked ?? 0} sản phẩm`);
      close();
      onDone();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Tooltip title={topicId === undefined ? "Chọn một nhóm chủ đề ở bên trái trước" : undefined}>
        <Button icon={<UploadOutlined />} disabled={topicId === undefined} onClick={() => setOpened(true)}>
          Nhập link đã chuyển đổi
        </Button>
      </Tooltip>
      <Modal
        title="Nhập link đã chuyển đổi"
        open={opened}
        width={820}
        onCancel={close}
        onOk={confirm}
        okText={preview ? `Gắn link cho ${preview.ok} sản phẩm` : "Nhập"}
        cancelText="Đóng"
        okButtonProps={{ disabled: !preview || preview.ok === 0 }}
        confirmLoading={busy}
      >
        <Flex vertical gap={12}>
          <Typography.Text>
            Chọn file Shopee Affiliate › Custom Link trả về (CSV hoặc Excel). Chỉ sản phẩm do bạn thêm trong nhóm này
            được gắn link; link của đồng đội giữ nguyên.
          </Typography.Text>
          <Upload
            accept=".csv,.xlsx"
            maxCount={1}
            showUploadList={false}
            beforeUpload={(chosen) => {
              void choose(chosen);
              return false;
            }}
          >
            <Button icon={<UploadOutlined />} loading={busy}>
              {file ? file.name : "Chọn file kết quả (.csv hoặc .xlsx)"}
            </Button>
          </Upload>
          {preview && (
            <>
              <Alert
                type={preview.errors ? "warning" : "success"}
                showIcon
                message={`${preview.ok} sản phẩm sẽ được gắn link, ${preview.others} của đồng đội giữ nguyên, ${preview.errors} dòng lỗi`}
              />
              <Table<Row>
                size="small"
                rowKey="row"
                dataSource={preview.rows}
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                columns={[
                  { title: "Dòng", dataIndex: "row", width: 60 },
                  {
                    title: "Sản phẩm / link gốc",
                    key: "original",
                    render: (_, row) => <span style={{ wordBreak: "break-all" }}>{row.name ?? row.original}</span>,
                  },
                  {
                    title: "Kết quả",
                    key: "state",
                    width: 260,
                    render: (_, row) => (
                      <Flex vertical gap={2}>
                        <Tag color={STATE[row.state].color} style={{ width: "fit-content" }}>
                          {STATE[row.state].label}
                        </Tag>
                        {row.message && <Typography.Text type="secondary">{row.message}</Typography.Text>}
                      </Flex>
                    ),
                  },
                ]}
              />
            </>
          )}
        </Flex>
      </Modal>
    </>
  );
}
