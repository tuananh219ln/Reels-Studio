"use client";

import { SearchOutlined } from "@ant-design/icons";
import { App, Card, Flex, Input, Segmented, Select, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateProduct, type AffiliateVideo } from "@/lib/api";

/** What a member pastes as the reel's pinned comment: the script's sentence, then one link per product. */
function usable(product: AffiliateVideo["products"][number]): boolean {
  return product.status === "approved" && product.problems.length === 0;
}

/** Where a video stands with its products: none yet, every one fine, or one to look at again (yellow tag). */
type Linked = "all" | "none" | "linked" | "review";

function linkedState(video: AffiliateVideo): Exclude<Linked, "all"> {
  if (video.products.length === 0) return "none";
  return video.products.every(usable) ? "linked" : "review";
}

const LINKED: { value: Linked; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "none", label: "Chưa gắn sản phẩm" },
  { value: "linked", label: "Đã gắn" },
  { value: "review", label: "Cần xem lại" },
];

/** Lower case and one Unicode form, so a typed "Đ" or a composed vowel still finds the title. */
function folded(text: string): string {
  return text.normalize("NFC").toLocaleLowerCase("vi");
}

function pinnedText(video: AffiliateVideo): string {
  const links = video.products
    .filter((product) => usable(product) && product.url)
    .map((product) => `${product.name}: ${product.url}`);
  return [video.pinned_comment, ...links].filter(Boolean).join("\n");
}

/** The posted videos (Facebook reels, TikTok posts made by hand), each with the products attached to it. */
export default function PostedVideos() {
  const { message } = App.useApp();
  const [videos, setVideos] = useState<AffiliateVideo[]>([]);
  const [approved, setApproved] = useState<AffiliateProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<AffiliateVideo["platform"] | null>(null);
  const [linked, setLinked] = useState<Linked>("all");

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
          <Link prefetch={false} href={`/videos/${video.id}`}>
            {video.title}
          </Link>
          <Typography.Text type="secondary">
            <Tag>{video.platform === "tiktok" ? "TikTok" : "Facebook"}</Tag>
            {formatDateTime(video.published_at)}
          </Typography.Text>
          {video.reel_url && (
            <a href={video.reel_url} target="_blank" rel="noreferrer">
              {video.platform === "tiktok" ? "Xem bài TikTok" : "Xem Reel"}
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
        const wanted = video.platform === "tiktok" ? "tiktok_shop" : "shopee";
        const choices = [
          ...video.products.map((product) => ({ value: product.id, label: product.name })),
          ...approved
            .filter(
              (product) => !attached.has(product.id) && product.problems.length === 0 && product.platform === wanted,
            )
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
                <Tag key={product.id} color="warning" style={{ whiteSpace: "normal", marginInlineEnd: 0 }}>
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
        video.platform === "tiktok" ? (
          <Typography.Text type="secondary">Gắn giỏ trong app TikTok</Typography.Text>
        ) : video.products.some(usable) ? (
          <Typography.Text copyable={{ text: pinnedText(video), tooltips: ["Sao chép", "Đã sao chép"] }}>
            Sao chép
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">Chưa gắn link</Typography.Text>
        ),
    },
  ];

  // The search and platform narrow the videos first, so each tab counts what it would show.
  const words = folded(query.trim());
  const matching = videos.filter(
    (video) => (platform === null || video.platform === platform) && (!words || folded(video.title).includes(words)),
  );
  const counts = Object.fromEntries(
    LINKED.map(({ value }) => [
      value,
      value === "all" ? matching.length : matching.filter((video) => linkedState(video) === value).length,
    ]),
  ) as Record<Linked, number>;
  const shown = linked === "all" ? matching : matching.filter((video) => linkedState(video) === linked);
  const filtered = Boolean(words) || platform !== null || linked !== "all";

  return (
    <>
      <Flex wrap gap={12} align="center" style={{ marginBottom: 16 }}>
        <Segmented<Linked>
          aria-label="Lọc theo sản phẩm đã gắn"
          value={linked}
          onChange={setLinked}
          options={LINKED.map(({ value, label }) => ({ value, label: `${label} (${counts[value]})` }))}
          style={{ maxWidth: "100%", overflowX: "auto" }}
        />
        <Input
          aria-label="Tìm theo tiêu đề video"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề video"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 280, maxWidth: "100%" }}
        />
        <Select
          aria-label="Lọc theo nền tảng"
          placeholder="Mọi nền tảng"
          allowClear
          value={platform}
          onChange={(value) => setPlatform(value ?? null)}
          options={[
            { value: "facebook", label: "Facebook" },
            { value: "tiktok", label: "TikTok" },
          ]}
          style={{ width: 160 }}
        />
      </Flex>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<AffiliateVideo>
          rowKey="id"
          columns={columns}
          dataSource={shown}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 1000 }}
          locale={{ emptyText: filtered ? "Không có video nào khớp" : "Chưa có video nào đã đăng" }}
        />
      </Card>
    </>
  );
}
