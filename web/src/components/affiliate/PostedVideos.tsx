"use client";

import {
  AppstoreOutlined,
  CloseOutlined,
  FacebookFilled,
  ProfileOutlined,
  SearchOutlined,
  TableOutlined,
  TikTokFilled,
} from "@ant-design/icons";
import { App, Button, Card, Empty, Flex, Input, Segmented, Select, Table, Tabs, Tag, Tooltip, Typography } from "antd";
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
import VideoThumbnail from "@/components/VideoThumbnail";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";

type Product = AffiliateVideo["products"][number];

/** What a member pastes as the reel's pinned comment: the script's sentence, then one link per product. */
function usable(product: Product): boolean {
  return product.status === "approved" && product.problems.length === 0;
}

/** Where a video stands with its products: none yet, every one fine, one to look at again, or pasted by hand. */
type Linked = "all" | "none" | "linked" | "manual" | "review";

function linkedState(video: AffiliateVideo): Exclude<Linked, "all"> {
  if (video.manual_comment) return "manual";
  if (video.products.length === 0) return "none";
  return video.products.every(usable) ? "linked" : "review";
}

const LINKED: { value: Linked; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "none", label: "Chưa gắn" },
  { value: "linked", label: "Đã gắn" },
  { value: "manual", label: "Dán tay" },
  { value: "review", label: "Cần xem lại" },
];

/** Three ways to see the same videos: a low table to scan, cards with their covers, or a list beside one video. */
type View = "table" | "cards" | "detail";
const VIEW_KEY = "reels-studio.affiliate-videos-view";

function useView(): [View, (next: View) => void] {
  const [view, setView] = useState<View>(() => {
    try {
      const saved = window.localStorage.getItem(VIEW_KEY);
      return saved === "cards" || saved === "detail" ? saved : "table";
    } catch {
      return "table";
    }
  });
  function choose(next: View) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }
  return [view, choose];
}

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

/** How the video's Facebook comment stands, from its live posts; TikTok's cart is set in TikTok's app. */
function commentStatus(video: AffiliateVideo): { label: string; color?: string; tip?: string } {
  const facebook = video.posts.filter((post) => post.platform === "facebook");
  if (facebook.length === 0) {
    return { label: "Gắn giỏ trong app TikTok" };
  }
  if (video.manual_comment) {
    return { label: "Dán tay", color: "blue", tip: "Link đã dán tay trên Facebook: app không viết hay sửa bình luận" };
  }
  const failed = facebook.find((post) => post.comment === "failed");
  if (failed) {
    return { label: "Lỗi bình luận", color: "error", tip: failed.comment_error ?? undefined };
  }
  if (facebook.some((post) => post.comment === "pending")) {
    return { label: "Đang bình luận", color: "processing" };
  }
  if (facebook.some((post) => post.comment === "waiting")) {
    return { label: "Chờ app bình luận", color: "processing" };
  }
  if (facebook.some((post) => post.comment === "done")) {
    return { label: "App đã bình luận", color: "success" };
  }
  if (!video.products.some(usable)) {
    return { label: "Chờ gắn sản phẩm" };
  }
  return { label: "Chưa bình luận", tip: "Bấm “Bình luận ngay” ở Bài đăng, hoặc sao chép rồi dán tay" };
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
  const [fanpageId, setFanpageId] = useState<number | null>(null);
  const [linked, setLinked] = useState<Linked>("all");
  // "Lọc theo sản phẩm": only the videos a product is attached to, so each product shows where its link goes.
  const [productId, setProductId] = useState<number | null>(null);
  const [view, chooseView] = useView();
  const [openId, setOpenId] = useState<number | null>(null);

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

  async function save(video: AffiliateVideo, send: () => Promise<AffiliateVideo>) {
    // Each save sends the whole selection, so a second change must wait for the first answer.
    setSaving(video.id);
    try {
      const saved = await send();
      setVideos((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
    } catch (err) {
      message.error(errorMessage(err));
      await reload();
    } finally {
      setSaving(null);
    }
  }

  function attach(video: AffiliateVideo, productIds: number[]) {
    return save(video, () =>
      api<AffiliateVideo>(`/affiliate-products/videos/${video.id}`, "PUT", { product_ids: productIds }),
    );
  }

  function setManual(video: AffiliateVideo, manual: boolean) {
    return save(video, () => api<AffiliateVideo>(`/affiliate-products/videos/${video.id}/manual`, "PUT", { manual }));
  }

  /** "Facebook · time · Xem Reel", then one chip per Page or TikTok account; a teammate's names its owner. */
  function where(video: AffiliateVideo) {
    return (
      <>
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
        <Flex wrap gap={4}>
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
      </>
    );
  }

  function title(video: AffiliateVideo) {
    return (
      <Link prefetch={false} href={`/videos/${video.id}`} style={{ fontWeight: 500 }}>
        {video.title}
      </Link>
    );
  }

  /** The attached products as tags (× takes one off), "+ Gắn sản phẩm", then what to look at: a product that lost
   * its approval, and whose commission each link earns. The script's ideas show while nothing is attached. */
  function products(video: AffiliateVideo) {
    const attached = new Set(video.products.map((product) => product.id));
    const wanted = video.platform === "tiktok" ? "tiktok_shop" : "shopee";
    const choices = approved
      .filter((product) => !attached.has(product.id) && product.problems.length === 0 && product.platform === wanted)
      .map((product) => ({
        value: product.id,
        label:
          `${product.name} (~${product.expected_commission.toLocaleString("vi-VN")}đ)` +
          (product.created_by_id === me.id ? "" : ` · Người thêm: ${product.created_by}`),
      }));
    const ids = video.products.map((product) => product.id);
    return (
      <Flex vertical gap={6}>
        <Flex wrap gap={6} align="center">
          {video.products.map((product) => (
            <Tag
              key={product.id}
              color={usable(product) ? undefined : "warning"}
              closable={saving !== video.id}
              closeIcon={<CloseOutlined aria-label={`Bỏ ${product.name} khỏi video`} />}
              onClose={(event) => {
                event.preventDefault();
                void attach(
                  video,
                  ids.filter((id) => id !== product.id),
                );
              }}
              style={{ marginInlineEnd: 0, paddingBlock: 2 }}
            >
              {product.name}
            </Tag>
          ))}
          <Select<number>
            aria-label={`Sản phẩm của video ${video.title}`}
            placeholder="+ Gắn sản phẩm"
            size="small"
            showSearch
            optionFilterProp="label"
            disabled={saving === video.id}
            value={null}
            options={choices}
            notFoundContent="Không còn sản phẩm đã duyệt nào"
            onChange={(id) => void attach(video, [...ids, id])}
            popupMatchSelectWidth={320}
            style={{ width: 160 }}
          />
        </Flex>
        {video.products
          .filter((product) => !usable(product))
          .map((product) => (
            <Typography.Text key={product.id} type="warning" style={{ fontSize: 12 }}>
              {product.status === "approved" ? "Không còn đạt tiêu chí" : "Đã bỏ duyệt"}: {product.name}
            </Typography.Text>
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
        {video.products.length === 0 && video.suggestions.length > 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Gợi ý: {video.suggestions.join("; ")}
          </Typography.Text>
        )}
      </Flex>
    );
  }

  /** The comment's state, "Sao chép" for pasting it by hand, and "Đã dán link tay" / "Bỏ dán tay". */
  function comment(video: AffiliateVideo) {
    const status = commentStatus(video);
    const onFacebook = video.posts.some((post) => post.platform === "facebook");
    return (
      <Flex vertical gap={6} align="flex-start">
        <Tooltip title={status.tip}>
          <Tag color={status.color} style={{ marginInlineEnd: 0 }} data-testid="comment-status">
            {status.label}
          </Tag>
        </Tooltip>
        {onFacebook && video.products.some(usable) && (
          <Typography.Text copyable={{ text: pinnedText(video), tooltips: ["Sao chép", "Đã sao chép"] }}>
            Sao chép
          </Typography.Text>
        )}
        {onFacebook && (
          <Tooltip
            title={
              video.manual_comment
                ? "App sẽ viết bình luận như bình thường"
                : "Đã dán link trên Facebook: app không viết hay sửa bình luận của video này, sản phẩm chỉ để ghi nhận"
            }
          >
            <Button
              size="small"
              type={video.manual_comment ? "default" : "dashed"}
              disabled={saving === video.id}
              onClick={() => void setManual(video, !video.manual_comment)}
            >
              {video.manual_comment ? "Bỏ dán tay" : "Đã dán link tay"}
            </Button>
          </Tooltip>
        )}
      </Flex>
    );
  }

  // The filters narrow the videos first, so each tab counts what it would show.
  const words = folded(query.trim());
  const mineCount = videos.filter((video) => video.mine).length;
  const whose = whosePick ?? (mineCount > 0 ? "mine" : "all");
  const matching = videos.filter(
    (video) =>
      (whose === "all" || video.mine) &&
      (platform === null || video.platform === platform) &&
      (fanpageId === null || video.posts.some((post) => post.fanpage_id === fanpageId)) &&
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
  // The Pages the videos are on, mine first.
  const pages = new Map<number, { label: string; mine: boolean }>();
  for (const video of videos) {
    for (const post of video.posts) {
      if (post.fanpage_id !== null && !pages.has(post.fanpage_id)) {
        const mine = post.owner_id === me.id;
        pages.set(post.fanpage_id, {
          label: mine ? (post.name ?? "") : `${post.name} · ${post.owner_name ?? "chưa có chủ"}`,
          mine,
        });
      }
    }
  }
  const pageOptions = [...pages.entries()]
    .sort((a, b) => Number(b[1].mine) - Number(a[1].mine) || a[1].label.localeCompare(b[1].label, "vi"))
    .map(([id, { label }]) => ({ value: id, label }));
  const counts = Object.fromEntries(
    LINKED.map(({ value }) => [
      value,
      value === "all" ? matching.length : matching.filter((video) => linkedState(video) === value).length,
    ]),
  ) as Record<Linked, number>;
  const shown = linked === "all" ? matching : matching.filter((video) => linkedState(video) === linked);
  const filtered = Boolean(words) || platform !== null || fanpageId !== null || linked !== "all" || productId !== null;
  const emptyText = filtered
    ? "Không có video nào khớp"
    : whose === "mine" && videos.length > 0
      ? "Bạn chưa có video nào đã đăng. Chọn “Cả đội” để xem của mọi người."
      : "Chưa có video nào đã đăng";

  const columns: ColumnsType<AffiliateVideo> = [
    {
      title: "Video",
      key: "video",
      render: (_, video) => (
        <Flex gap={12} align="flex-start">
          <VideoThumbnail name={video.title} url={video.thumbnail_url} width={40} />
          <Flex vertical gap={4} style={{ minWidth: 0 }}>
            {title(video)}
            {where(video)}
          </Flex>
        </Flex>
      ),
    },
    { title: "Sản phẩm", key: "products", width: 400, render: (_, video) => products(video) },
    { title: "Bình luận", key: "comment", width: 170, render: (_, video) => comment(video) },
  ];

  const open = shown.find((video) => video.id === openId) ?? shown[0];

  return (
    <>
      <Flex wrap gap={12} align="center" style={{ marginBottom: 4 }}>
        <WhoseFilter value={whose} onChange={setWhose} mine={mineCount} all={videos.length} />
        <Input
          aria-label="Tìm theo tiêu đề video"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề video"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ flex: "1 1 200px", maxWidth: 320 }}
        />
        <FilterSelect
          aria-label="Lọc theo Page"
          placeholder="Mọi Page"
          value={fanpageId}
          onChange={(value) => setFanpageId(value ?? null)}
          options={pageOptions}
          style={{ width: 200 }}
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
          style={{ width: 150 }}
        />
        <FilterSelect
          aria-label="Lọc theo sản phẩm"
          placeholder="Mọi sản phẩm"
          value={productId}
          onChange={(value) => setProductId(value ?? null)}
          options={productOptions}
          notFoundContent="Chưa video nào gắn sản phẩm"
          style={{ width: 220, maxWidth: "100%" }}
        />
        <Segmented<View>
          aria-label="Kiểu hiển thị"
          value={view}
          onChange={chooseView}
          style={{ marginLeft: "auto" }}
          options={[
            { value: "table", icon: <TableOutlined />, title: "Dạng bảng" },
            { value: "cards", icon: <AppstoreOutlined />, title: "Dạng thẻ" },
            { value: "detail", icon: <ProfileOutlined />, title: "Danh sách và chi tiết" },
          ]}
        />
      </Flex>
      <div aria-label="Lọc theo sản phẩm đã gắn" role="group">
        <Tabs
          activeKey={linked}
          onChange={(key) => setLinked(key as Linked)}
          items={LINKED.map(({ value, label }) => ({ key: value, label: `${label} (${counts[value]})` }))}
        />
      </div>

      {view === "table" && (
        <Card styles={{ body: { padding: 0 } }}>
          <Table<AffiliateVideo>
            rowKey="id"
            columns={columns}
            dataSource={shown}
            loading={loading}
            pagination={{ pageSize: 50, hideOnSinglePage: true }}
            scroll={{ x: 900 }}
            locale={{ emptyText }}
          />
        </Card>
      )}

      {view === "cards" &&
        (shown.length === 0 ? (
          <Empty description={loading ? "Đang tải…" : emptyText} />
        ) : (
          <div
            style={{
              display: "grid",
              gap: 12,
              gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 340px), 1fr))",
            }}
          >
            {shown.map((video) => (
              <Card key={video.id} size="small" data-testid="video-card">
                <Flex gap={12} align="flex-start">
                  <VideoThumbnail name={video.title} url={video.thumbnail_url} width={72} />
                  <Flex vertical gap={6} style={{ minWidth: 0, flex: 1 }}>
                    {title(video)}
                    {where(video)}
                    {products(video)}
                    {comment(video)}
                  </Flex>
                </Flex>
              </Card>
            ))}
          </div>
        ))}

      {view === "detail" &&
        (shown.length === 0 || !open ? (
          <Empty description={loading ? "Đang tải…" : emptyText} />
        ) : (
          <div
            style={{
              display: "grid",
              gap: 16,
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))",
              alignItems: "start",
            }}
          >
            <Card size="small" styles={{ body: { padding: 4 } }}>
              {shown.map((video) => {
                const status = commentStatus(video);
                return (
                  <button
                    key={video.id}
                    type="button"
                    onClick={() => setOpenId(video.id)}
                    aria-current={video.id === open.id}
                    style={{
                      display: "flex",
                      gap: 10,
                      width: "100%",
                      padding: 8,
                      border: 0,
                      borderRadius: 8,
                      textAlign: "left",
                      cursor: "pointer",
                      background: video.id === open.id ? "var(--ant-color-primary-bg)" : "transparent",
                    }}
                  >
                    <VideoThumbnail name={video.title} url={video.thumbnail_url} width={32} />
                    <Flex vertical gap={2} style={{ minWidth: 0 }}>
                      <Typography.Text strong ellipsis>
                        {video.title}
                      </Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {formatDateTime(video.published_at)} · {video.products.length} sản phẩm
                      </Typography.Text>
                      <span>
                        <Tag color={status.color} style={{ marginInlineEnd: 0 }}>
                          {status.label}
                        </Tag>
                      </span>
                    </Flex>
                  </button>
                );
              })}
            </Card>
            <Card size="small" data-testid="video-detail">
              <Flex gap={16} align="flex-start">
                <VideoThumbnail name={open.title} url={open.thumbnail_url} width={96} />
                <Flex vertical gap={8} style={{ minWidth: 0, flex: 1 }}>
                  {title(open)}
                  {where(open)}
                  <Typography.Text type="secondary">Sản phẩm</Typography.Text>
                  {products(open)}
                  {open.suggestions.length > 0 && open.products.length > 0 && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      Gợi ý từ kịch bản: {open.suggestions.join("; ")}
                    </Typography.Text>
                  )}
                  <Typography.Text type="secondary">Bình luận</Typography.Text>
                  {comment(open)}
                </Flex>
              </Flex>
            </Card>
          </div>
        ))}
    </>
  );
}
