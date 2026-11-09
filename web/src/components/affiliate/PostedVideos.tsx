"use client";

import { FacebookFilled, SearchOutlined, TikTokFilled } from "@ant-design/icons";
import { App, Card, Flex, Input, Segmented, Select, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  errorMessage,
  formatDateTime,
  type AffiliateCommission,
  type AffiliateProduct,
  type AffiliateVideo,
} from "@/lib/api";
import FilterSelect from "@/components/FilterSelect";
import { useMe } from "@/components/MeContext";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";

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

/** One short line per Page where the product's commission is not the member's own: whose it is, or that the product
 * will not be in that Page's comment at all (the Page is named only when the video is on several). Nothing is
 * refused: a teammate's video may carry a member's product. */
function commissionNote(product: string, line: AffiliateCommission, named: boolean): string {
  const what = named ? `${product} · ${line.fanpage_name}` : product;
  if (line.kind === "no_link") {
    return `${what} → không có trong bình luận (chưa có link)`;
  }
  return `${what} → hoa hồng về ${line.user_name} (${line.kind === "saved_link" ? "link lưu sẵn" : "tài khoản Shopee của Page"})`;
}

/** The whole reason, on hover. */
function commissionWhy(line: AffiliateCommission): string {
  const page = `Page ${line.fanpage_name}`;
  if (line.kind === "no_link") {
    return `${page} chưa có tài khoản Shopee dùng được (có App ID) và sản phẩm chưa có link affiliate lưu sẵn, nên sản phẩm bị bỏ khỏi bình luận của Page này.`;
  }
  if (line.kind === "saved_link") {
    return `${page} chưa có tài khoản Shopee dùng được, nên bình luận dùng link lưu sẵn của người thêm sản phẩm (${line.user_name}); hoa hồng về tài khoản đó.`;
  }
  return `${page} có tài khoản Shopee riêng của chủ Page (${line.user_name}); link trong bình luận do tài khoản đó tạo nên hoa hồng về đó.`;
}

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
  const { me } = useMe();
  const [videos, setVideos] = useState<AffiliateVideo[]>([]);
  // "Của tôi" or "Cả đội"; null until chosen (the default follows whether the member has a posted video).
  const [whosePick, setWhose] = useState<Whose | null>(null);
  const [approved, setApproved] = useState<AffiliateProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<AffiliateVideo["platform"] | null>(null);
  const [linked, setLinked] = useState<Linked>("all");
  // "Lọc theo sản phẩm": only the videos a product is attached to, so each product shows where its link goes.
  const [productId, setProductId] = useState<number | null>(null);

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
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {video.platform === "tiktok" ? "TikTok" : "Facebook"} · {formatDateTime(video.published_at)}
            {video.reel_url && (
              <>
                {" · "}
                <a href={video.reel_url} target="_blank" rel="noreferrer">
                  {video.platform === "tiktok" ? "Xem bài TikTok" : "Xem Reel"}
                </a>
              </>
            )}
          </Typography.Text>
          {/* Where it is live: one chip per Page or TikTok account; a teammate's names its owner, who gets its money. */}
          <Flex wrap gap={4} style={{ marginTop: 2 }}>
            {video.posts.map((post, index) => {
              const theirs = post.owner_id !== me.id;
              const owner = post.owner_name ?? "chưa có chủ";
              const kind = post.platform === "tiktok" ? "Tài khoản TikTok" : "Page";
              const Icon = post.platform === "tiktok" ? TikTokFilled : FacebookFilled;
              return (
                <Tooltip
                  key={index}
                  title={theirs ? `${kind} của ${owner}: hoa hồng ở đây về ${owner}` : `${kind} của bạn`}
                >
                  <Tag
                    bordered={false}
                    color={theirs ? "gold" : undefined}
                    icon={<Icon />}
                    style={{ marginInlineEnd: 0 }}
                    data-testid="video-post"
                  >
                    {post.name ?? "không rõ"}
                    {theirs ? ` · ${owner}` : ""}
                  </Tag>
                </Tooltip>
              );
            })}
          </Flex>
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
              label:
                `${product.name} (~${product.expected_commission.toLocaleString("vi-VN")}đ)` +
                (product.created_by_id === me.id ? "" : ` · Người thêm: ${product.created_by}`),
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
            {video.products.flatMap((product) =>
              product.commission
                .filter((line) => line.kind === "no_link" || line.user_id !== me.id)
                .map((line) => (
                  <Tooltip key={`${product.id}-${line.fanpage_id}`} title={commissionWhy(line)}>
                    <Typography.Text
                      type={line.kind === "no_link" ? "danger" : "warning"}
                      style={{ fontSize: 12 }}
                      data-testid="commission-note"
                    >
                      {commissionNote(product.name, line, product.commission.length > 1)}
                    </Typography.Text>
                  </Tooltip>
                )),
            )}
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
  const mineCount = videos.filter((video) => video.mine).length;
  const whose = whosePick ?? (mineCount > 0 ? "mine" : "all");
  const matching = videos.filter(
    (video) =>
      (whose === "all" || video.mine) &&
      (platform === null || video.platform === platform) &&
      (!words || folded(video.title).includes(words)) &&
      (productId === null || video.products.some((product) => product.id === productId)),
  );
  // The products attached to at least one video, with how many, most used first.
  const uses = new Map<number, { name: string; count: number }>();
  for (const video of videos) {
    for (const product of video.products) {
      const seen = uses.get(product.id);
      uses.set(product.id, { name: product.name, count: (seen?.count ?? 0) + 1 });
    }
  }
  const productOptions = [...uses.entries()]
    .sort((a, b) => b[1].count - a[1].count || a[1].name.localeCompare(b[1].name, "vi"))
    .map(([id, { name, count }]) => ({ value: id, label: `${name} (${count} video)` }));
  const counts = Object.fromEntries(
    LINKED.map(({ value }) => [
      value,
      value === "all" ? matching.length : matching.filter((video) => linkedState(video) === value).length,
    ]),
  ) as Record<Linked, number>;
  const shown = linked === "all" ? matching : matching.filter((video) => linkedState(video) === linked);
  const filtered = Boolean(words) || platform !== null || linked !== "all" || productId !== null;

  return (
    <>
      {/* Whose and which first, the products' state on a row of its own, so the two switches never sit side by side. */}
      <Flex wrap gap={12} align="center" style={{ marginBottom: 12 }}>
        <WhoseFilter value={whose} onChange={setWhose} mine={mineCount} all={videos.length} />
        <Input
          aria-label="Tìm theo tiêu đề video"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề video"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 240, maxWidth: "100%" }}
        />
        <FilterSelect
          aria-label="Lọc theo nền tảng"
          placeholder="Mọi nền tảng"
          value={platform}
          onChange={(value) => setPlatform(value ?? null)}
          options={[
            { value: "facebook", label: "Facebook" },
            { value: "tiktok", label: "TikTok" },
          ]}
          style={{ width: 160 }}
        />
        <FilterSelect
          aria-label="Lọc theo sản phẩm"
          placeholder="Mọi sản phẩm"
          value={productId}
          onChange={(value) => setProductId(value ?? null)}
          options={productOptions}
          notFoundContent="Chưa video nào gắn sản phẩm"
          style={{ width: 240, maxWidth: "100%" }}
        />
      </Flex>
      <Segmented<Linked>
        aria-label="Lọc theo sản phẩm đã gắn"
        value={linked}
        onChange={setLinked}
        options={LINKED.map(({ value, label }) => ({ value, label: `${label} (${counts[value]})` }))}
        style={{ maxWidth: "100%", overflowX: "auto", marginBottom: 16 }}
      />
      <Card styles={{ body: { padding: 0 } }}>
        <Table<AffiliateVideo>
          rowKey="id"
          columns={columns}
          dataSource={shown}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 1000 }}
          locale={{
            emptyText: filtered
              ? "Không có video nào khớp"
              : whose === "mine" && videos.length > 0
                ? "Bạn chưa có video nào đã đăng. Chọn “Cả đội” để xem của mọi người."
                : "Chưa có video nào đã đăng",
          }}
        />
      </Card>
    </>
  );
}
