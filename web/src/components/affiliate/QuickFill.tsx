"use client";

import { App, Button, Flex, InputNumber, Select, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";

/** A Shopee product nobody has read yet: a pasted link or a row of Shopee Affiliate's file, with no Shopee App ID in
 * the team to fill in its stars, sales and shop type. */
function unread(product: AffiliateProduct): boolean {
  return product.shop_type === "other" && product.rating === 0 && product.sold === 0;
}

/** A Shopee draft whose stars or sales are under the approval rule: unread, or read or typed short. */
export function needsQuickFill(product: AffiliateProduct): boolean {
  return (
    product.platform === "shopee" &&
    product.status === "draft" &&
    product.lookup !== "pending" &&
    product.short_on_counts
  );
}

/** Fills those three in on the row itself, from the product's Shopee page, so the row can be approved without opening
 * "Sửa" for each one. Saves through the same call as "Sửa". */
export default function QuickFill({
  product,
  options,
  onSaved,
}: {
  product: AffiliateProduct;
  options: AffiliateOptions;
  onSaved: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const fresh = unread(product);
  // An unread product starts empty, so each value is read off its page; otherwise from what it holds.
  const [shopType, setShopType] = useState<string | undefined>(fresh ? undefined : product.shop_type);
  const [rating, setRating] = useState<number | null>(fresh ? null : product.rating);
  const [sold, setSold] = useState<number | null>(fresh ? null : product.sold);
  const [busy, setBusy] = useState(false);
  const page = product.page_url ?? product.url ?? undefined;
  const ready = shopType !== undefined && rating !== null && sold !== null;

  async function save() {
    if (!ready) {
      return;
    }
    setBusy(true);
    try {
      await api(`/affiliate-products/${product.id}`, "PUT", {
        knowledge_topic_id: product.knowledge_topic_id,
        platform: product.platform,
        name: product.name,
        url: product.url,
        shop_name: product.shop_name,
        shop_type: shopType,
        rating,
        sold,
        price: product.price,
        commission_rate: product.commission_rate,
      });
      message.success("Đã lưu, xem lại rồi bấm Duyệt");
      await onSaved();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex vertical gap={6} align="flex-start" data-testid="quick-fill" style={{ marginTop: 4 }}>
      <Typography.Text type="secondary">
        {fresh ? "Chưa có App ID Shopee nên cần điền tay" : "Sửa nhanh số sao, lượt bán"}, xem trên{" "}
        <a href={page} target="_blank" rel="noreferrer">
          trang sản phẩm
        </a>
        :
      </Typography.Text>
      <Select
        aria-label={`Loại shop của ${product.name}`}
        placeholder="Loại shop"
        size="small"
        value={shopType}
        onChange={setShopType}
        options={options.shop_types.shopee}
        style={{ width: "100%" }}
      />
      <Flex gap={6}>
        <InputNumber
          aria-label={`Số sao của ${product.name}`}
          placeholder="Sao"
          size="small"
          min={0}
          max={5}
          step={0.1}
          value={rating}
          onChange={setRating}
          style={{ width: 80 }}
        />
        <InputNumber
          aria-label={`Lượt bán của ${product.name}`}
          placeholder="Đã bán"
          size="small"
          min={0}
          precision={0}
          value={sold}
          onChange={setSold}
          style={{ width: 110 }}
        />
        <Button size="small" type="primary" disabled={!ready} loading={busy} onClick={save}>
          Lưu
        </Button>
      </Flex>
    </Flex>
  );
}
