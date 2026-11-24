"use client";
import { errorMessage } from "@/lib/api";
import { App, Checkbox, Flex, Modal, Typography } from "antd";
import { useState } from "react";

/** "Xuất file Custom Link": the group's approved products as the Excel file Shopee's Custom Link page takes
 * (docs/decisions/2026-11-24-custom-link-excel.md). The group is the one open on the left; "Nhập / Xuất" opens it. */
export default function CustomLinkExport({
  open,
  onClose,
  topicId,
  topicName,
}: {
  open: boolean;
  onClose: () => void;
  topicId?: number;
  topicName?: string;
}) {
  const { message } = App.useApp();
  const [includeLinked, setIncludeLinked] = useState(false);
  const [busy, setBusy] = useState(false);

  async function download() {
    if (topicId === undefined) {
      return;
    }
    setBusy(true);
    try {
      const query = new URLSearchParams({ topic_id: String(topicId), include_linked: String(includeLinked) });
      const response = await fetch(`/api/affiliate-products/custom-link/export.xlsx?${query}`, { cache: "no-store" });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.message ?? "Không xuất được file");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `custom-link-nhom-${topicId}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Xuất file Custom Link"
      open={open}
      onCancel={onClose}
      onOk={download}
      okText="Tải file Excel"
      cancelText="Đóng"
      confirmLoading={busy}
    >
      <Flex vertical gap={12}>
        <Typography.Text>
          Nhóm “{topicName}”: các sản phẩm đã duyệt do bạn thêm, chưa có link affiliate. Tải file lên Shopee Affiliate ›
          Custom Link, rồi nhập file kết quả về bằng “Nhập link đã chuyển đổi”.
        </Typography.Text>
        <Checkbox checked={includeLinked} onChange={(event) => setIncludeLinked(event.target.checked)}>
          Gồm cả món đã có link
        </Checkbox>
        <Typography.Text type="secondary">
          Mỗi dòng gắn Sub_id1 là Page của nhóm, nên đơn chỉ đo được tới Page, không biết từ video nào.
        </Typography.Text>
      </Flex>
    </Modal>
  );
}
