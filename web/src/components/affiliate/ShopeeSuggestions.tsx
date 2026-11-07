"use client";

import { SearchOutlined } from "@ant-design/icons";
import { App, Alert, Button, Flex, Image, Input, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import ProductModal from "@/components/affiliate/ProductModal";
import {
  api,
  errorMessage,
  formatDateTime,
  type AffiliateOptions,
  type AffiliateProduct,
  type AffiliateSuggestions,
} from "@/lib/api";

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

/** Shopee's suggestions for the product ideas of a video or an article ("Bài viết"), searched by the worker with the
 * member's own Shopee account. "Chọn" approves a product meeting the rules and attaches it; each Page's own link is
 * made when its comment is written. Without an account, each idea opens Shopee Affiliate's own search instead.
 * `base` is the owner's address under the api (".../videos/<id>" or ".../articles/<id>"). */
export default function ShopeeSuggestions({
  base,
  ideas,
  state,
  searchedAt,
  attachedIds,
  onChanged,
}: {
  base: string;
  ideas: string[];
  /** The owner's own search state and when its last search finished: a change of either reloads the list. The time
   * matters because the worker can finish a search before the owner is reloaded, so it never shows as pending. */
  state: string;
  searchedAt: string | null;
  attachedIds: number[];
  /** Reload the owner after a change (a choice, a search finished). */
  onChanged: () => Promise<void>;
}) {
  const { message } = App.useApp();
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
      setData(await api<AffiliateSuggestions>(`${base}/suggestions`));
    } catch {
      setData(null);
    }
  }, [base]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load, state, searchedAt]);

  // While the worker searches or reads a pasted link, ask again every few seconds until it has answered.
  const pending = data?.state === "pending";
  const reading = !!data?.keywords.some((group) => group.products.some((product) => product.lookup === "pending"));
  useEffect(() => {
    if (!pending && !reading) return;
    const timer = setTimeout(async () => {
      await load();
      await onChanged();
    }, 3000);
    return () => clearTimeout(timer);
  }, [pending, reading, data, load, onChanged]);

  async function call(run: () => Promise<AffiliateSuggestions>) {
    setBusy(true);
    try {
      setData(await run());
      await onChanged();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const search = () => call(() => api(`${base}/suggestions`, "POST"));
  const choose = (productId: number) => call(() => api(`${base}/choose`, "POST", { product_id: productId }));
  const attached = new Set(data?.attached_ids ?? attachedIds);
  const searched = data?.keywords.filter((group) => !group.pasted) ?? [];

  async function paste() {
    const links = lines(pasted);
    if (links.length === 0) return;
    await call(() => api(`${base}/links`, "POST", { links }));
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
          disabled={ideas.length === 0}
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
      {searched.length === 0 && ideas.length > 0 && (
        <Space size={4} wrap>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Chưa có tài khoản Shopee có App ID? Tìm tay (bấm để copy từ khoá rồi dán vào ô tìm kiếm của Shopee
            Affiliate):
          </Typography.Text>
          {ideas.map((keyword) => (
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
