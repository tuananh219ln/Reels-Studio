"use client";

import { App, Card, Flex, Select, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateProduct, type AffiliateVideo } from "@/lib/api";

/** What a member pastes as the reel's pinned comment: the script's sentence, then one link per product. */
function usable(product: AffiliateVideo["products"][number]): boolean {
  return product.status === "approved" && product.problems.length === 0;
}

function pinnedText(video: AffiliateVideo): string {
  const links = video.products.filter(usable).map((product) => `${product.name}: ${product.url}`);
  return [video.pinned_comment, ...links].filter(Boolean).join("\n");
}

/** The reels on the Facebook Page, each with the products attached to it. */
export default function PostedVideos() {
  const { message } = App.useApp();
  const [videos, setVideos] = useState<AffiliateVideo[]>([]);
  const [approved, setApproved] = useState<AffiliateProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

  const reload = useCallback(async () => {
    try {
      const [loadedVideos, loadedProducts] = await Promise.all([
        api<AffiliateVideo[]>("/affiliate-products/videos"),
        api<AffiliateProduct[]>("/affiliate-products?status=approved"),
      ]);
      setVideos(loadedVideos);
      setApproved(loadedProducts);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void reload();
  }, [reload]);

  async function attach(video: AffiliateVideo, productIds: number[]) {
    // Each save sends the whole selection, so a second pick must wait for the first answer.
    setSaving(video.id);
    try {
      const saved = await api<AffiliateVideo>(`/affiliate-products/videos/${video.id}`, "PUT", {
        product_ids: productIds,
      });
      setVideos((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
    } catch (err) {
      message.error(errorMessage(err));
      await reload();
    } finally {
      setSaving(null);
    }
  }

  const columns: ColumnsType<AffiliateVideo> = [
    {
      title: "Video",
      key: "video",
      render: (_, video) => (
        <Flex vertical gap={2}>
          <Link href={`/videos/${video.id}`}>{video.title}</Link>
          <Typography.Text type="secondary">{formatDateTime(video.published_at)}</Typography.Text>
          {video.reel_url && (
            <a href={video.reel_url} target="_blank" rel="noreferrer">
              Xem Reel
            </a>
          )}
        </Flex>
      ),
    },
    {
      title: "Gợi ý từ kịch bản",
      key: "suggestions",
      width: 240,
      render: (_, video) => video.suggestions.join("; "),
    },
    {
      title: "Sản phẩm gắn với video",
      key: "products",
      width: 380,
      render: (_, video) => {
        const attached = new Set(video.products.map((product) => product.id));
        const choices = [
          ...video.products.map((product) => ({ value: product.id, label: product.name })),
          ...approved
            .filter((product) => !attached.has(product.id) && product.problems.length === 0)
            .map((product) => ({
              value: product.id,
              label: `${product.name} (~${product.expected_commission.toLocaleString("vi-VN")}đ)`,
            })),
        ];
        return (
          <Flex vertical gap={6}>
            <Select
              mode="multiple"
              aria-label={`Sản phẩm của video ${video.title}`}
              placeholder="Chọn sản phẩm đã duyệt"
              optionFilterProp="label"
              disabled={saving === video.id}
              value={video.products.map((product) => product.id)}
              options={choices}
              onChange={(ids: number[]) => attach(video, ids)}
              style={{ width: "100%" }}
            />
            {video.products
              .filter((product) => !usable(product))
              .map((product) => (
                <Tag key={product.id} color="warning" style={{ whiteSpace: "normal" }}>
                  {product.status === "approved" ? "Không còn đạt tiêu chí" : "Đã bỏ duyệt"}: {product.name}
                </Tag>
              ))}
          </Flex>
        );
      },
    },
    {
      title: "Bình luận ghim",
      key: "comment",
      width: 150,
      render: (_, video) =>
        video.products.some(usable) ? (
          <Typography.Text copyable={{ text: pinnedText(video), tooltips: ["Sao chép", "Đã sao chép"] }}>
            Sao chép
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">Chưa gắn link</Typography.Text>
        ),
    },
  ];

  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Table<AffiliateVideo>
        rowKey="id"
        columns={columns}
        dataSource={videos}
        loading={loading}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        scroll={{ x: 1000 }}
        locale={{ emptyText: "Chưa có video nào đã đăng" }}
      />
    </Card>
  );
}
