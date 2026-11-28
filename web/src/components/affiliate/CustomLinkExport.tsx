"use client";
import { errorMessage } from "@/lib/api";
import { convertShopeeLinks, convertedFile, useShopeeConvert } from "@/lib/shopeeExtension";
import { Alert, App, Button, Checkbox, Flex, Modal, Select, Typography } from "antd";
import { useState } from "react";

/** "Xuất file Custom Link": the group's approved products as the Excel file Shopee's Custom Link page takes
 * (docs/decisions/2026-11-24-custom-link-excel.md). The group is the one open on the left; "Nhập / Xuất" opens it. */
export default function CustomLinkExport({
  open,
  onClose,
  topicId,
  topicName,
  pages,
  onConverted,
}: {
  open: boolean;
  onClose: () => void;
  topicId?: number;
  topicName?: string;
  /** The Pages that post the group: with two or more, the file is for one of them. */
  pages: { id: number; name: string }[];
  /** The converted links, as a file for "Nhập link đã chuyển đổi" to preview. */
  onConverted: (file: File) => void;
}) {
  const { message } = App.useApp();
  const [includeLinked, setIncludeLinked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pageId, setPageId] = useState<number>();
  const several = pages.length > 1;
  const extension = useShopeeConvert();
  const [problem, setProblem] = useState<string>();

  async function convert() {
    if (topicId === undefined) {
      return;
    }
    setBusy(true);
    setProblem(undefined);
    try {
      const query = new URLSearchParams({ topic_id: String(topicId), include_linked: String(includeLinked) });
      if (several && pageId) query.set("fanpage_id", String(pageId));
      const response = await fetch(`/api/affiliate-products/custom-link/links?${query}`, { cache: "no-store" });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.message ?? "Không lấy được danh sách link");
      }
      const answer = await convertShopeeLinks(data.links, data.sub_id1);
      if (answer.error === "login") {
        setProblem("Chưa đăng nhập Shopee Affiliate. Đăng nhập affiliate.shopee.vn trên Chrome này rồi bấm lại.");
        return;
      }
      if (answer.error || !answer.rows) {
        const detail = answer.detail ? ` (mã ${answer.detail.status ?? "?"}: ${answer.detail.body ?? ""})` : "";
        setProblem(`Shopee không trả lời như mong đợi, hãy dùng file Excel bên dưới.${detail}`);
        return;
      }
      onConverted(convertedFile(answer.rows));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    if (topicId === undefined) {
      return;
    }
    setBusy(true);
    try {
      const query = new URLSearchParams({ topic_id: String(topicId), include_linked: String(includeLinked) });
      if (several && pageId) query.set("fanpage_id", String(pageId));
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
      okButtonProps={{ disabled: several && !pageId }}
    >
      <Flex vertical gap={12}>
        <Typography.Text>
          Nhóm “{topicName}”: các sản phẩm đã duyệt do bạn thêm, chưa có link affiliate. Tải file lên Shopee Affiliate ›
          Custom Link, rồi nhập file kết quả về bằng “Nhập link đã chuyển đổi”.
        </Typography.Text>
        {several && (
          <Flex vertical gap={8}>
            <Select
              aria-label="Page của file"
              placeholder="Chọn Page để gắn đơn về"
              value={pageId}
              onChange={setPageId}
              options={pages.map((page) => ({ value: page.id, label: page.name }))}
            />
            <Alert
              type="warning"
              showIcon
              message="Nhóm có nhiều Page: mỗi sản phẩm chỉ có một link, nên đơn chỉ đo về Page đã chọn. Đơn từ các Page còn lại vẫn về tài khoản của bạn nhưng không gắn riêng được cho Page đó."
            />
          </Flex>
        )}
        <Checkbox checked={includeLinked} onChange={(event) => setIncludeLinked(event.target.checked)}>
          Gồm cả món đã có link
        </Checkbox>
        {extension && (
          <Flex vertical gap={8}>
            <Button type="primary" onClick={convert} loading={busy} disabled={several && !pageId}>
              Chuyển bằng tiện ích Chrome
            </Button>
            <Typography.Text type="secondary">
              Tiện ích tự chuyển link trong tab Shopee Affiliate của bạn (cần đã đăng nhập), rồi cho bạn xem trước kết
              quả. Dùng file Excel nếu cách này không chạy.
            </Typography.Text>
            {problem && <Alert type="warning" showIcon message={problem} />}
          </Flex>
        )}
        <Typography.Text type="secondary">
          Mỗi dòng gắn Sub_id1 là Page của nhóm, nên đơn chỉ đo được tới Page, không biết từ video nào.
        </Typography.Text>
      </Flex>
    </Modal>
  );
}
