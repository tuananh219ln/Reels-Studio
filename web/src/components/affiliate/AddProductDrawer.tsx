"use client";

import { InboxOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Form, Input, Segmented, Select, Typography, Upload } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, type AffiliateImport, type AffiliateOptions } from "@/lib/api";
import FormDrawer from "@/components/FormDrawer";

export type AddMode = "links" | "file";

const MAX_FILE_BYTES = 2_000_000;

/** "Thêm sản phẩm": paste Shopee links or drop Shopee Affiliate's file, and the rest is filled in by itself. Typing
 * every field stays possible ("Nhập tay"), for TikTok Shop and for a team without a Shopee App ID. */
export default function AddProductDrawer({
  mode,
  options,
  onClose,
  onManual,
  onDone,
}: {
  /** null: closed. */
  mode: AddMode | null;
  options: AffiliateOptions;
  onClose: () => void;
  onManual: () => void;
  onDone: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [tab, setTab] = useState<AddMode>("links");
  const [topicId, setTopicId] = useState<number>();
  const [links, setLinks] = useState("");
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [result, setResult] = useState<AffiliateImport | null>(null);
  const [busy, setBusy] = useState(false);
  const [openedAs, setOpenedAs] = useState<AddMode | null>(null);

  // Each opening starts clean on the tab it was opened for (state adjusted while rendering, not in an effect).
  if (mode !== openedAs) {
    setOpenedAs(mode);
    if (mode !== null) {
      setTab(mode);
      setLinks("");
      setFile(null);
      setResult(null);
    }
  }

  // With one topic group there is nothing to choose.
  const topic = topicId ?? (options.topics.length === 1 ? options.topics[0].id : undefined);
  const pasted = links
    .split(/\s+/)
    .map((link) => link.trim())
    .filter(Boolean);
  const ready = topic !== undefined && (tab === "links" ? pasted.length > 0 && options.shopee_lookup : file !== null);

  async function submit() {
    if (!ready) {
      return;
    }
    setBusy(true);
    try {
      if (tab === "links") {
        const done = await api<{ added: number; skipped: string[] }>("/affiliate-products/links", "POST", {
          knowledge_topic_id: topic,
          links: pasted,
        });
        const skipped = done.skipped.length > 0 ? `, ${done.skipped.length} link đã có trong danh sách` : "";
        message.success(`Đã thêm ${done.added} sản phẩm, đang lấy thông tin từ Shopee${skipped}`);
        await onDone();
        onClose();
        return;
      }
      const done = await api<AffiliateImport>("/affiliate-products/import", "POST", {
        knowledge_topic_id: topic,
        text: file?.text ?? "",
      });
      const counts = [`thêm ${done.added}`, done.updated > 0 ? `cập nhật ${done.updated}` : ""].filter(Boolean);
      message.success(`Đã nhập: ${counts.join(", ")} sản phẩm`);
      if (done.errors.length > 0 || !done.lookup) {
        // Stay open so the member reads which rows were left out and what is still to fill in.
        setResult(done);
        setFile(null);
        await onDone();
        return;
      }
      await onDone();
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Thêm sản phẩm"
      open={mode !== null}
      onClose={onClose}
      onOk={submit}
      okText={tab === "links" ? "Thêm" : "Nhập"}
      confirmLoading={busy}
      okButtonProps={{ disabled: !ready }}
      width={560}
    >
      <Flex vertical gap={16}>
        <Segmented<AddMode>
          block
          aria-label="Cách thêm"
          value={tab}
          onChange={(next) => {
            setTab(next);
            setResult(null);
          }}
          options={[
            { value: "links", label: "Dán link Shopee" },
            { value: "file", label: "Nhập file" },
          ]}
        />
        <Form layout="vertical" requiredMark={false} component="div">
          <Form.Item label="Nhóm chủ đề" required>
            <Select
              aria-label="Nhóm chủ đề"
              placeholder="Chọn nhóm chủ đề"
              value={topic}
              onChange={setTopicId}
              options={options.topics.map((topic) => ({ value: topic.id, label: topic.name }))}
            />
          </Form.Item>
          {tab === "links" ? (
            <>
              {!options.shopee_lookup && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  title="Cần một tài khoản Shopee có App ID để tự lấy thông tin từ link"
                  description={
                    <>
                      Thêm App ID và Secret ở{" "}
                      <Link href="/settings/affiliate-accounts">Cài đặt › Tài khoản affiliate</Link>. Chưa có thì dùng{" "}
                      <Typography.Link onClick={() => setTab("file")}>Nhập file</Typography.Link> từ Shopee Affiliate.
                    </>
                  }
                />
              )}
              <Form.Item
                label="Link sản phẩm"
                extra="Mỗi dòng một link, tối đa 50. Tên, shop, số sao, lượt bán, giá và hoa hồng được lấy từ Shopee sau vài giây; link bạn dán được giữ làm link affiliate."
              >
                <Input.TextArea
                  aria-label="Link sản phẩm"
                  value={links}
                  onChange={(event) => setLinks(event.target.value)}
                  placeholder={"https://s.shopee.vn/...\nhttps://shopee.vn/..."}
                  autoSize={{ minRows: 4, maxRows: 12 }}
                  disabled={!options.shopee_lookup}
                />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              label="File từ Shopee Affiliate"
              extra="Trong Shopee Affiliate, mở Lấy link hàng loạt, tạo link rồi tải file CSV về và thả vào đây. Sản phẩm đã có trong danh sách được cập nhật link và hoa hồng."
            >
              <Upload.Dragger
                accept=".csv,text/csv"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(picked) => {
                  if (picked.size > MAX_FILE_BYTES) {
                    message.error("File quá lớn, hãy chia nhỏ");
                    return Upload.LIST_IGNORE;
                  }
                  picked.text().then(
                    (text) => {
                      setFile({ name: picked.name, text });
                      setResult(null);
                    },
                    () => message.error("Không đọc được file"),
                  );
                  return false;
                }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">{file ? file.name : "Bấm hoặc kéo file CSV vào đây"}</p>
              </Upload.Dragger>
            </Form.Item>
          )}
        </Form>
        {result && (
          <Alert
            type={result.errors.length > 0 ? "warning" : "info"}
            showIcon
            title={`Đã nhập ${result.added + result.updated} sản phẩm${
              result.errors.length > 0 ? `, bỏ qua ${result.errors.length} dòng` : ""
            }`}
            description={
              <Flex vertical gap={4}>
                {result.errors.map((error) => (
                  <span key={error.row}>
                    Dòng {error.row}: {error.message}
                  </span>
                ))}
                {!result.lookup && (
                  <span>
                    File không có số sao, lượt bán và loại shop: điền ngay trên dòng của từng sản phẩm trong danh sách
                    rồi duyệt, hoặc thêm App ID Shopee để chúng được lấy tự động.
                  </span>
                )}
              </Flex>
            }
          />
        )}
        <Typography.Text type="secondary">
          Sản phẩm TikTok Shop hoặc muốn tự điền từng ô?{" "}
          <Button type="link" size="small" style={{ padding: 0 }} onClick={onManual}>
            Nhập tay
          </Button>
        </Typography.Text>
      </Flex>
    </FormDrawer>
  );
}
