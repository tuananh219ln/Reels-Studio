"use client";

import { Alert, App, Form, Input, InputNumber, Modal, Select } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";

type Fields = Pick<
  AffiliateProduct,
  | "knowledge_topic_id"
  | "platform"
  | "name"
  | "url"
  | "shop_name"
  | "shop_type"
  | "rating"
  | "sold"
  | "price"
  | "commission_rate"
>;

/** Adds a product, or edits one; saving a change to an approved product sends it back to draft. */
export default function ProductModal({
  target,
  options,
  onClose,
  onDone,
}: {
  target: AffiliateProduct | "new" | null;
  options: AffiliateOptions;
  onClose: () => void;
  onDone: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<Fields>();
  const [busy, setBusy] = useState(false);
  const adding = target === "new";
  const platform = Form.useWatch("platform", form) ?? "shopee";

  useEffect(() => {
    if (target === null) {
      return;
    }
    form.resetFields();
    form.setFieldsValue(target === "new" ? { platform: "shopee" } : { ...target, url: target.url ?? undefined });
  }, [form, target]);

  async function submit(fields: Fields) {
    if (target === null) {
      return;
    }
    setBusy(true);
    try {
      await (target === "new"
        ? api("/affiliate-products", "POST", fields)
        : api(`/affiliate-products/${target.id}`, "PUT", fields));
      await onDone();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={adding ? "Thêm sản phẩm" : "Sửa sản phẩm"}
      open={target !== null}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText={adding ? "Thêm" : "Lưu"}
      cancelText="Huỷ"
      confirmLoading={busy}
      forceRender
    >
      {target !== null && target !== "new" && target.status === "approved" && (
        <Alert
          type="warning"
          showIcon
          title="Đổi thông tin sẽ đưa sản phẩm về nháp, cần duyệt lại."
          style={{ marginBottom: 16 }}
        />
      )}
      <Form form={form} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item label="Nền tảng" name="platform" rules={[{ required: true, message: "Chọn nền tảng" }]}>
          <Select
            aria-label="Nền tảng"
            options={options.platforms}
            onChange={() => form.setFieldValue("shop_type", undefined)}
          />
        </Form.Item>
        <Form.Item
          label="Nhóm chủ đề"
          name="knowledge_topic_id"
          rules={[{ required: true, message: "Chọn nhóm chủ đề" }]}
        >
          <Select
            aria-label="Nhóm chủ đề"
            options={options.topics.map((topic) => ({ value: topic.id, label: topic.name }))}
          />
        </Form.Item>
        <Form.Item
          label="Tên sản phẩm"
          name="name"
          rules={[
            { required: true, whitespace: true, message: "Nhập tên sản phẩm" },
            { max: 300, message: "Tên tối đa 300 ký tự" },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          label={platform === "tiktok_shop" ? "Link sản phẩm TikTok Shop" : "Link affiliate"}
          name="url"
          rules={[
            {
              required: platform === "shopee" && !(target !== null && target !== "new" && target.from_shopee_api),
              whitespace: true,
              message: "Dán link affiliate",
            },
          ]}
          extra={
            platform === "tiktok_shop"
              ? "Không bắt buộc. Sản phẩm TikTok Shop được gắn giỏ trong app TikTok, không có bình luận chứa link."
              : "Tạo link trong trang Shopee Affiliate rồi dán vào đây. Fanpage đã gắn tài khoản Shopee có App ID sẽ dùng link riêng của tài khoản đó."
          }
        >
          <Input />
        </Form.Item>
        <Form.Item
          label="Tên shop"
          name="shop_name"
          rules={[{ required: true, whitespace: true, message: "Nhập tên shop" }]}
        >
          <Input />
        </Form.Item>
        <Form.Item label="Loại shop" name="shop_type" rules={[{ required: true, message: "Chọn loại shop" }]}>
          <Select aria-label="Loại shop" options={options.shop_types[platform as keyof typeof options.shop_types]} />
        </Form.Item>
        <Form.Item label="Số sao" name="rating" rules={[{ required: true, message: "Nhập số sao" }]}>
          <InputNumber min={0} max={5} step={0.1} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="Lượt bán" name="sold" rules={[{ required: true, message: "Nhập lượt bán" }]}>
          <InputNumber min={0} precision={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="Giá (đ)" name="price" rules={[{ required: true, message: "Nhập giá" }]}>
          <InputNumber min={1} precision={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          label="Hoa hồng (%)"
          name="commission_rate"
          rules={[{ required: true, message: "Nhập tỷ lệ hoa hồng" }]}
          extra="Tổng tỷ lệ hiển thị trong trang Shopee Affiliate, gồm cả XTRA nếu có."
        >
          <InputNumber min={0} max={100} step={0.1} style={{ width: "100%" }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
