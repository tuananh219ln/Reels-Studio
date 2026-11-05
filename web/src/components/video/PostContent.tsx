"use client";

import { CopyOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Flex, Image, Input, Select, Space, Tag, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ProductModal from "@/components/affiliate/ProductModal";
import {
  api,
  errorMessage,
  formatDateTime,
  type AffiliateOptions,
  type AffiliateProduct,
  type AffiliateSuggestions,
  type VideoDetail,
} from "@/lib/api";
import AutoSaveField, { useEditor } from "./AutoSaveField";

type PostFields = Pick<VideoDetail, "caption" | "hashtags" | "affiliates" | "pinned_comment" | "music_suggestions">;

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
const words = (text: string) => text.split(/\s+/).filter(Boolean);

export default function PostContent({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const patch = (body: Partial<PostFields>) => api<VideoDetail>(`/videos/${video.id}`, "PATCH", body);
  const warningsFor = (field: string) =>
    video.video_warnings.filter((warning) => warning.field === field).map((warning) => warning.message);

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success(`Đã copy ${what}`);
    } catch {
      message.error("Trình duyệt không cho copy, hãy chọn chữ rồi copy tay");
    }
  }

  return (
    <Card title="Nội dung đăng" size="small">
      <Flex vertical gap={4}>
        <AutoSaveField
          label="Caption"
          value={video.caption}
          multiline
          rows={5}
          save={(caption) => patch({ caption })}
        />
        <Warnings messages={warningsFor("caption")} />
        <AutoSaveField
          label="Hashtag"
          value={video.hashtags.join(" ")}
          placeholder="#xuongkhop #duongsinh"
          save={(text) => patch({ hashtags: words(text) })}
        />
        <AutoSaveField
          label="Gợi ý sản phẩm (AI)"
          value={video.affiliates.join("\n")}
          multiline
          hint={
            video.platform === "tiktok"
              ? "Từ khoá để tìm sản phẩm trong mục “Thêm sản phẩm” của app TikTok; mỗi dòng một sản phẩm"
              : "Từ khoá app dùng để tìm sản phẩm trên Shopee; mỗi dòng một sản phẩm"
          }
          save={(text) => patch({ affiliates: lines(text) })}
        />
        {video.platform === "facebook" && <ShopeeSuggestions video={video} />}
        <AttachedProducts video={video} />
        <AutoSaveField
          label="Bình luận ghim"
          value={video.pinned_comment}
          multiline
          save={(pinned_comment) => patch({ pinned_comment })}
        />
        <Warnings messages={warningsFor("pinned_comment")} />
        <AutoSaveField
          label="Gợi ý nhạc"
          value={video.music_suggestions.join("\n")}
          multiline
          hint="Tìm tên nhạc này trong TikTok hoặc Facebook khi đăng; mỗi dòng một bản"
          save={(text) => patch({ music_suggestions: lines(text) })}
        />
        <Flex wrap gap={8} style={{ marginBottom: 12 }}>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.post_text, "caption + hashtag")}>
            Copy caption + hashtag
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.pinned_comment, "bình luận ghim")}>
            Copy bình luận ghim
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.music_suggestions.join("\n"), "gợi ý nhạc")}>
            Copy gợi ý nhạc
          </Button>
        </Flex>
        <Typography.Text strong>Tự rà soát an toàn của AI</Typography.Text>
        {video.hand_written ? (
          <Alert
            type="warning"
            showIcon
            data-testid="hand-written-review"
            title="Video tự viết nên chưa được AI rà soát an toàn. Hãy tự kiểm tra nội dung theo luật an toàn của kênh trước khi đăng."
          />
        ) : video.self_review.length ? (
          <ul style={{ margin: "4px 0 0", paddingLeft: 20 }} data-testid="self-review">
            {video.self_review.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <Typography.Text type="secondary">Không có câu nào phải sửa</Typography.Text>
        )}
      </Flex>
    </Card>
  );
}

function Warnings({ messages }: { messages: string[] }) {
  return messages.map((text) => <Alert key={text} type="warning" showIcon title={text} style={{ marginBottom: 8 }} />);
}

/** Shopee's suggestions for the video's product ideas, searched by the worker with the member's own Shopee account.
 * "Chọn" approves a product meeting the rules and attaches it; each Page's own link is made when its comment is
 * written. Without an account, each idea opens Shopee Affiliate's own search instead. */
function ShopeeSuggestions({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const [data, setData] = useState<AffiliateSuggestions | null>(null);
  const [busy, setBusy] = useState(false);
  const [pasted, setPasted] = useState("");
  // "Sửa thông tin" on a pasted product: the same form as on /affiliate, its choices asked for on first use.
  const [editing, setEditing] = useState<AffiliateProduct | null>(null);
  const [options, setOptions] = useState<AffiliateOptions | null>(null);

  async function copyKeyword(keyword: string) {
    try {
      await navigator.clipboard.writeText(keyword);
      message.success(`Đã copy "${keyword}", dán vào ô "Tìm kiếm" của Shopee Affiliate`);
    } catch {
      message.warning(`Trình duyệt không cho copy, hãy gõ "${keyword}" vào ô "Tìm kiếm" của Shopee Affiliate`);
    }
  }

  const load = useCallback(async () => {
    try {
      setData(await api<AffiliateSuggestions>(`/affiliate-products/videos/${video.id}/suggestions`));
    } catch {
      setData(null);
    }
  }, [video.id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load, video.suggest.state]);

  // While the worker searches or reads a pasted link, ask again every few seconds until it has answered.
  const pending = data?.state === "pending";
  const reading = !!data?.keywords.some((group) => group.products.some((product) => product.lookup === "pending"));
  useEffect(() => {
    if (!pending && !reading) return;
    const timer = setTimeout(async () => {
      await load();
      onSaved(await api<VideoDetail>(`/videos/${video.id}`));
    }, 3000);
    return () => clearTimeout(timer);
  }, [pending, reading, data, load, onSaved, video.id]);

  async function call(run: () => Promise<AffiliateSuggestions>) {
    setBusy(true);
    try {
      setData(await run());
      onSaved(await api<VideoDetail>(`/videos/${video.id}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const search = () => call(() => api(`/affiliate-products/videos/${video.id}/suggestions`, "POST"));
  const choose = (productId: number) =>
    call(() => api(`/affiliate-products/videos/${video.id}/choose`, "POST", { product_id: productId }));
  const attached = new Set(data?.attached_ids ?? video.affiliate_product_ids);
  const searched = data?.keywords.filter((group) => !group.pasted) ?? [];

  async function paste() {
    const links = lines(pasted);
    if (links.length === 0) return;
    await call(() => api(`/affiliate-products/videos/${video.id}/links`, "POST", { links }));
    setPasted("");
  }

  async function edit(product: AffiliateProduct) {
    try {
      setOptions(options ?? (await api<AffiliateOptions>("/affiliate-products/options")));
      setEditing(product);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Flex vertical gap={6} style={{ marginBottom: 12 }} data-testid="shopee-suggestions">
      <Flex justify="space-between" align="center" gap={8} wrap>
        <Typography.Text strong>Sản phẩm gợi ý từ Shopee</Typography.Text>
        <Button
          size="small"
          icon={<SearchOutlined />}
          loading={busy || pending}
          disabled={video.affiliates.length === 0}
          onClick={search}
        >
          {searched.length ? "Tìm lại" : "Tìm sản phẩm"}
        </Button>
      </Flex>
      {pending && <Typography.Text type="secondary">Đang tìm trên Shopee…</Typography.Text>}
      {data?.error && <Alert type="warning" showIcon title={data.error} />}
      {data?.at && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Tìm lúc {formatDateTime(data.at)}; chỉ hiện sản phẩm đạt tiêu chí (từ 4.7 sao, từ 100 lượt bán).
        </Typography.Text>
      )}
      {data?.keywords.map((group) => (
        <Flex vertical gap={4} key={group.keyword}>
          <Typography.Text type="secondary">{group.keyword}</Typography.Text>
          {group.products.length === 0 && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Không có sản phẩm nào đạt tiêu chí
            </Typography.Text>
          )}
          {group.products.map((product) => (
            <Flex key={product.id} gap={8} align="center" data-testid="suggested-product">
              {product.image_url && (
                <Image
                  src={product.image_url}
                  alt=""
                  width={40}
                  height={40}
                  preview={false}
                  style={{ borderRadius: 4 }}
                />
              )}
              <Flex vertical gap={0} style={{ minWidth: 0, flex: 1 }}>
                <Typography.Link
                  href={product.page_url ?? product.url ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  ellipsis
                >
                  {product.name}
                </Typography.Link>
                {product.lookup === "pending" ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    Đang lấy thông tin từ Shopee…
                  </Typography.Text>
                ) : product.price === 0 ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    Chưa có thông tin sản phẩm
                  </Typography.Text>
                ) : (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {product.price.toLocaleString("vi-VN")}đ, {product.rating} sao,{" "}
                    {product.sold.toLocaleString("vi-VN")} đã bán, {product.shop_type_label}, hoa hồng{" "}
                    {product.commission_rate}% (~{product.expected_commission.toLocaleString("vi-VN")}đ/đơn)
                  </Typography.Text>
                )}
                {product.lookup === "failed" && product.lookup_error && (
                  <Typography.Text type="danger" style={{ fontSize: 12 }}>
                    {product.lookup_error}
                  </Typography.Text>
                )}
                {product.lookup !== "pending" && product.problems.length > 0 && !attached.has(product.id) && (
                  <Typography.Text type="warning" style={{ fontSize: 12 }} data-testid="suggested-problems">
                    Chưa chọn được: {product.problems.join("; ")}
                  </Typography.Text>
                )}
              </Flex>
              {attached.has(product.id) ? (
                <Tag color="success">Đã chọn</Tag>
              ) : product.problems.length > 0 ? (
                <Button size="small" disabled={busy || product.lookup === "pending"} onClick={() => void edit(product)}>
                  Sửa thông tin
                </Button>
              ) : (
                <Button size="small" disabled={busy} onClick={() => choose(product.id)}>
                  Chọn
                </Button>
              )}
            </Flex>
          ))}
        </Flex>
      ))}
      {searched.length === 0 && video.affiliates.length > 0 && (
        <Space size={4} wrap>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Chưa có tài khoản Shopee có App ID? Tìm tay (bấm để copy từ khoá rồi dán vào ô tìm kiếm của Shopee
            Affiliate):
          </Typography.Text>
          {video.affiliates.map((keyword) => (
            <Typography.Link
              key={keyword}
              style={{ fontSize: 12 }}
              // Shopee Affiliate ignores a keyword in the address, so the click copies it for the search box.
              href="https://affiliate.shopee.vn/offer/product_offer"
              target="_blank"
              rel="noreferrer"
              onClick={() => copyKeyword(keyword)}
            >
              {keyword}
            </Typography.Link>
          ))}
        </Space>
      )}
      {/* The link from Shopee Affiliate's "Lấy link" pasted straight here, without its "Lấy link hàng loạt" file. */}
      <Flex gap={8} align="flex-start">
        <Input.TextArea
          aria-label="Dán link aff Shopee"
          placeholder="Dán link aff Shopee (s.shopee.vn/…), mỗi dòng một link"
          autoSize={{ minRows: 1, maxRows: 4 }}
          value={pasted}
          onChange={(event) => setPasted(event.target.value)}
        />
        <Button disabled={busy || lines(pasted).length === 0} onClick={() => void paste()}>
          Thêm link
        </Button>
      </Flex>
      {options && (
        <ProductModal
          target={editing}
          options={options}
          onClose={() => setEditing(null)}
          onDone={async () => {
            message.success("Đã lưu");
            setEditing(null);
            await load();
          }}
        />
      )}
    </Flex>
  );
}

/** The approved products attached to the video: on Facebook their links go in the comment the worker writes under
 * the reel, after the pinned comment; on TikTok they are the cart a member adds in TikTok's app. Chosen before
 * posting so the first comment already holds them; a change edits a comment already written. */
function AttachedProducts({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const [products, setProducts] = useState<AffiliateProduct[] | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    const platform = video.platform === "tiktok" ? "tiktok_shop" : "shopee";
    api<AffiliateProduct[]>(`/affiliate-products?status=approved&platform=${platform}`).then(
      (found) => live && setProducts(found),
      () => live && setProducts([]),
    );
    return () => {
      live = false;
    };
  }, [video.platform, video.affiliate_product_ids]);

  async function save(ids: number[]) {
    setSaving(true);
    try {
      await api(`/affiliate-products/videos/${video.id}`, "PUT", { product_ids: ids });
      onSaved(await api<VideoDetail>(`/videos/${video.id}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const usable = (products ?? []).filter((product) => product.problems.length === 0);
  const label = video.platform === "tiktok" ? "Sản phẩm TikTok Shop gắn giỏ" : "Sản phẩm Shopee trong bình luận";
  return (
    <Flex vertical gap={4} style={{ marginBottom: 12 }}>
      <Typography.Text strong>{label}</Typography.Text>
      <Select
        mode="multiple"
        aria-label={label}
        placeholder="Chọn sản phẩm đã duyệt"
        loading={products === null || saving}
        value={video.affiliate_product_ids}
        onChange={save}
        optionFilterProp="label"
        options={usable.map((product) => ({ value: product.id, label: product.name }))}
        notFoundContent={
          <Typography.Text type="secondary">
            Chưa có sản phẩm đã duyệt. Thêm ở <Link href="/affiliate">Affiliate</Link>.
          </Typography.Text>
        }
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {video.platform === "tiktok"
          ? "Gắn giỏ các sản phẩm này trong app TikTok khi đăng; TikTok không có bình luận chứa link."
          : "Link các sản phẩm này đi sau bình luận ghim, trong bình luận app tự viết dưới reel. Fanpage gắn tài khoản Shopee dùng link riêng của tài khoản đó."}
      </Typography.Text>
    </Flex>
  );
}
