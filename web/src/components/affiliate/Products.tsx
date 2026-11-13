"use client";
import ProductActions from "@/components/actions/ProductActions";

import EmptyState from "@/components/EmptyState";
import FilterSelect from "@/components/FilterSelect";
import { useMe } from "@/components/MeContext";
import StatusText from "@/components/StatusText";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";
import { api, errorMessage, formatDateTime, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";
import { useUrlChoice, useUrlId, useUrlPage } from "@/lib/urlState";
import {
  CheckOutlined,
  DeleteOutlined,
  DownloadOutlined,
  LoadingOutlined,
  PlusOutlined,
  SearchOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Segmented, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import AddProductDrawer, { type AddMode } from "./AddProductDrawer";
import PlacesChip from "./PlacesChip";
import ProductModal from "./ProductModal";
import QuickFill, { needsQuickFill } from "./QuickFill";

type Filters = { topicId?: number; platform?: string; q: string };

/** The tabs over the list: everything, drafts short on stars or sales, drafts ready to approve, approved. */
type Stage = "all" | "fill" | "waiting" | "approved";

function stageOf(product: AffiliateProduct): Exclude<Stage, "all"> {
  if (product.status === "approved") return "approved";
  return product.short_on_counts ? "fill" : "waiting";
}

const STAGES: { value: Stage; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "fill", label: "Cần điền sao, lượt bán" },
  { value: "waiting", label: "Chờ duyệt" },
  { value: "approved", label: "Đã duyệt" },
];

/** The product list by topic group (the groups on the left, mine first, each with the Pages that post it), best
 * expected commission first. */
export default function Products() {
  // The table's page is in the address too, back to 1 when a filter changes.
  const tablePage = useUrlPage();
  const { message } = App.useApp();
  const { me } = useMe();
  // The search and filters are in the address (the Affiliate page clears them when its tab changes).
  const [search, setSearch] = useUrlChoice<string>("q", "");
  const [topicParam, setTopicParam] = useUrlId("group");
  const [platformParam, setPlatformParam] = useUrlChoice<string | null>("platform", null);
  const q = search;
  const topicId = topicParam ?? undefined;
  const platform = platformParam ?? undefined;
  const filters: Filters = { q, topicId, platform };
  const setFilters = (next: Filters) => {
    setSearch(next.q);
    setTopicParam(next.topicId ?? null);
    setPlatformParam(next.platform ?? null);
  };
  const [options, setOptions] = useState<AffiliateOptions>({
    platforms: [],
    shop_types: { shopee: [], tiktok_shop: [] },
    topics: [],
    pages: [],
    shopee_lookup: false,
  });
  const [products, setProducts] = useState<AffiliateProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<AffiliateProduct | "new" | null>(null);
  const [adding, setAdding] = useState<AddMode | null>(null);
  // "Tôi thêm" or "Cả đội"; null until chosen (the default follows whether the member has added a product).
  const [whosePick, setWhose] = useUrlChoice<Whose | null>("whose", null, ["mine", "all"]);
  const [stage, setStage] = useUrlChoice<Stage>("stage", "all", ["fill", "waiting", "approved"]);
  // The rows ticked for "Xoá đã chọn"; only the ones still listed count, so a filter never deletes hidden rows.
  const [ticked, setTicked] = useState<number[]>([]);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    const values: [string, string | undefined][] = [
      ["topic_id", topicId?.toString()],
      ["platform", platform],
      ["q", q.trim()],
    ];
    for (const [name, value] of values) {
      if (value) {
        params.set(name, value);
      }
    }
    return params.toString();
  }, [topicId, platform, q]);

  const reload = useCallback(
    async (quiet = false) => {
      setLoading(!quiet);
      try {
        setProducts(await api<AffiliateProduct[]>(`/affiliate-products?${query}`));
      } catch (err) {
        message.error(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [message, query],
  );

  useEffect(() => {
    const timer = setTimeout(reload, 250);
    return () => clearTimeout(timer);
  }, [reload]);

  const pending = products.some((product) => product.lookup === "pending");
  useEffect(() => {
    // The worker reads a pasted link within seconds; the list follows it without a reload.
    if (!pending) {
      return;
    }
    const timer = setInterval(() => void reload(true), 3000);
    return () => clearInterval(timer);
  }, [pending, reload]);

  const loadOptions = useCallback(() => {
    // Without the lists the selects stay empty and the api still refuses unknown values.
    api<AffiliateOptions>("/affiliate-products/options").then(setOptions, () => undefined);
  }, []);

  useEffect(loadOptions, [loadOptions]);

  const mineCount = products.filter((product) => product.created_by_id === me.id).length;
  const whose = whosePick ?? (mineCount > 0 ? "mine" : "all");
  const whoseRows = products.filter((product) => whose === "all" || product.created_by_id === me.id);
  const stageCounts = Object.fromEntries(
    STAGES.map(({ value }) => [
      value,
      value === "all" ? whoseRows.length : whoseRows.filter((product) => stageOf(product) === value).length,
    ]),
  ) as Record<Stage, number>;
  const shown = stage === "all" ? whoseRows : whoseRows.filter((product) => stageOf(product) === stage);
  // "Xuất CSV" follows the group, platform and search, and the stage as far as the api knows it (draft or approved).
  const exportQuery = [query, stage === "approved" ? "status=approved" : stage === "all" ? "" : "status=draft"]
    .filter(Boolean)
    .join("&");
  const open = options.topics.find((topic) => topic.id === topicId);
  const pagesOf = (id: number) => options.pages.filter((page) => page.knowledge_topic_id === id);

  const listed = new Set(shown.map((product) => product.id));
  const selected = ticked.filter((id) => listed.has(id));

  async function approveSelected() {
    try {
      const { approved, skipped } = await api<{ approved: number; skipped: number }>(
        "/affiliate-products/approve",
        "POST",
        { product_ids: selected },
      );
      const note = skipped ? `; ${skipped} sản phẩm chưa đạt tiêu chí nên vẫn là nháp` : "";
      (skipped ? message.warning : message.success)(`Đã duyệt ${approved} sản phẩm${note}`);
      setTicked([]);
    } catch (err) {
      message.error(errorMessage(err));
    }
    await reload();
  }

  async function deleteSelected() {
    try {
      const { deleted } = await api<{ deleted: number }>("/affiliate-products/delete", "POST", {
        product_ids: selected,
      });
      message.success(`Đã xoá ${deleted} sản phẩm`);
      setTicked([]);
    } catch (err) {
      message.error(errorMessage(err));
    }
    await reload();
  }

  const columns: ColumnsType<AffiliateProduct> = [
    {
      title: "Sản phẩm",
      key: "name",
      render: (_, product) => {
        const link = product.url ?? product.page_url ?? undefined;
        return (
          <Flex vertical gap={2}>
            <a href={link} target="_blank" rel="noreferrer" style={{ wordBreak: "break-word" }}>
              {product.name}
            </a>
            {product.lookup === "pending" && (
              <Typography.Text type="secondary">
                <LoadingOutlined /> Đang lấy thông tin từ Shopee…
              </Typography.Text>
            )}
            {product.lookup === "failed" && <Typography.Text type="danger">{product.lookup_error}</Typography.Text>}
            <Space size={4} wrap>
              <Tag>{product.platform_label}</Tag>
              {product.from_shopee_api && <Tag>Tìm qua API</Tag>}
              {topicId === undefined && <Typography.Text type="secondary">{product.topic}</Typography.Text>}
            </Space>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              <Tooltip title="Link lưu sẵn của sản phẩm được dùng trong bình luận khi Page đăng bài chưa có tài khoản Shopee dùng được.">
                <span>Người thêm: {product.created_by_id === me.id ? "bạn" : product.created_by}</span>
              </Tooltip>
              {product.video_count > 0 && `, ${product.video_count} video`}
            </Typography.Text>
            {product.url ? (
              <Typography.Text
                copyable={{ text: product.url, tooltips: ["Sao chép link", "Đã sao chép"] }}
                type="secondary"
              >
                Link
              </Typography.Text>
            ) : (
              product.platform === "shopee" && (
                <Typography.Text type="secondary">Link riêng theo tài khoản Shopee của từng Fanpage</Typography.Text>
              )
            )}
          </Flex>
        );
      },
    },
    {
      title: "Shop",
      key: "shop",
      width: 200,
      render: (_, product) => (
        <Flex vertical gap={2}>
          <span>{product.shop_name || "—"}</span>
          <Typography.Text type="secondary">{product.shop_type_label}</Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Sao / đã bán",
      key: "trust",
      width: 120,
      render: (_, product) =>
        product.lookup === "pending" ? "—" : `${product.rating} / ${product.sold.toLocaleString("vi-VN")}`,
    },
    {
      title: "Hoa hồng ước tính",
      key: "commission",
      width: 150,
      render: (_, product) => (
        <Flex vertical gap={2}>
          <Typography.Text strong>{product.expected_commission.toLocaleString("vi-VN")}đ/đơn</Typography.Text>
          <Typography.Text type="secondary">
            {product.commission_rate}%{product.price > 0 ? ` của ${product.price.toLocaleString("vi-VN")}đ` : ""}
          </Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Trạng thái",
      key: "status",
      width: 260,
      render: (_, product) =>
        product.lookup === "pending" ? (
          <StatusText tone="idle">Đang lấy thông tin</StatusText>
        ) : product.status === "approved" ? (
          <Flex vertical gap={2} align="flex-start">
            <StatusText tone="success">Đã duyệt</StatusText>
            {product.checked_at && (
              <Typography.Text type="secondary">
                {product.checked_by}, {formatDateTime(product.checked_at)}
              </Typography.Text>
            )}
            {product.problems.map((problem) => (
              <Typography.Text key={problem} type="warning">
                {problem}
              </Typography.Text>
            ))}
          </Flex>
        ) : (
          <Flex vertical gap={2} align="flex-start">
            <StatusText tone="idle">Nháp</StatusText>
            {product.problems.map((problem) => (
              <Typography.Text key={problem} type="warning">
                {problem}
              </Typography.Text>
            ))}
            {needsQuickFill(product) && <QuickFill product={product} options={options} onSaved={() => reload(true)} />}
          </Flex>
        ),
    },
    {
      title: "Thao tác",
      key: "actions",
      width: 230,
      render: (_, product) => <ProductActions product={product} onEdit={setTarget} onChanged={() => reload(true)} />,
    },
  ];

  /** One group on the left: its name, how many products it holds, and the Pages that post it. */
  function group(id: number | undefined, name: string, count: number) {
    const chosen = topicId === id;
    const pages = id === undefined ? [] : pagesOf(id);
    return (
      <button
        key={id ?? "all"}
        type="button"
        aria-pressed={chosen}
        onClick={() => {
          setFilters({ ...filters, topicId: id });
          setTicked([]);
        }}
        style={{
          display: "block",
          width: "100%",
          padding: "8px 10px",
          border: 0,
          borderRadius: 8,
          textAlign: "left",
          cursor: "pointer",
          background: chosen ? "var(--ant-color-primary-bg)" : "transparent",
        }}
      >
        <Flex justify="space-between" gap={8}>
          <Typography.Text strong={chosen} style={{ color: chosen ? "var(--ant-color-primary)" : undefined }}>
            {name}
          </Typography.Text>
          <Typography.Text type="secondary">{count}</Typography.Text>
        </Flex>
        {id !== undefined && (
          <div style={{ marginTop: 2 }}>
            {pages.length === 0 ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Chưa Page nào đăng
              </Typography.Text>
            ) : (
              <PlacesChip
                places={pages.map((page) => ({
                  platform: "facebook",
                  name: page.name,
                  owner: page.mine ? null : (page.owner_name ?? "chưa có chủ"),
                }))}
              />
            )}
          </div>
        )}
      </button>
    );
  }

  const myTopics = options.topics.filter((topic) => topic.mine);
  const otherTopics = options.topics.filter((topic) => !topic.mine);
  const total = options.topics.reduce((sum, topic) => sum + topic.product_count, 0);

  return (
    <Flex gap={16} align="flex-start" wrap>
      <Card size="small" style={{ flex: "0 0 260px", maxWidth: "100%" }} styles={{ body: { padding: 6 } }}>
        <nav aria-label="Nhóm chủ đề">
          {group(undefined, "Tất cả nhóm", total)}
          {myTopics.length > 0 && (
            <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, padding: "8px 10px 2px" }}>
              Nhóm của tôi
            </Typography.Text>
          )}
          {myTopics.map((topic) => group(topic.id, topic.name, topic.product_count))}
          {myTopics.length > 0 && otherTopics.length > 0 && (
            <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, padding: "8px 10px 2px" }}>
              Nhóm khác
            </Typography.Text>
          )}
          {otherTopics.map((topic) => group(topic.id, topic.name, topic.product_count))}
        </nav>
      </Card>
      <div style={{ flex: "1 1 520px", minWidth: 0 }}>
        <Flex wrap gap={12} justify="space-between" align="center" style={{ marginBottom: 12 }}>
          <Flex vertical gap={0}>
            <Typography.Text strong style={{ fontSize: 16 }} data-testid="product-group">
              {open ? open.name : "Tất cả nhóm"}
            </Typography.Text>
            {open && (
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                {pagesOf(open.id).length > 0
                  ? `Dùng cho video của ${pagesOf(open.id).length} Page`
                  : "Chưa Page nào đăng nhóm này"}
              </Typography.Text>
            )}
          </Flex>
          <Space wrap>
            <Button icon={<DownloadOutlined />} href={`/api/affiliate-products/export.csv?${exportQuery}`}>
              Xuất CSV
            </Button>
            <Button icon={<UploadOutlined />} onClick={() => setAdding("file")}>
              Nhập file
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding("links")}>
              Thêm sản phẩm
            </Button>
          </Space>
        </Flex>
        <Flex wrap gap={12} align="center">
          <Input
            aria-label="Tìm theo sản phẩm hoặc shop"
            prefix={<SearchOutlined />}
            placeholder="Tìm theo sản phẩm hoặc shop…"
            allowClear
            value={q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
            style={{ flex: "1 1 200px", maxWidth: 320 }}
          />
          <WhoseFilter value={whose} onChange={setWhose} mine={mineCount} all={products.length} mineLabel="Tôi thêm" />
          <FilterSelect
            aria-label="Lọc theo nền tảng"
            placeholder="Mọi nền tảng"
            value={platform}
            onChange={(value) => setFilters({ ...filters, platform: value })}
            options={options.platforms}
            style={{ width: 160 }}
          />
        </Flex>
        <div aria-label="Lọc theo trạng thái" role="group">
          {/* A filter, so it looks like one, not like a second row of the page's tabs. */}
          <Segmented<Stage>
            value={stage}
            onChange={setStage}
            options={STAGES.map(({ value, label }) => ({ value, label: `${label} (${stageCounts[value]})` }))}
          />
        </div>
        {selected.length > 0 && (
          <Flex gap={12} align="center" wrap style={{ marginBottom: 12 }} data-testid="product-selection">
            <Typography.Text>Đã chọn {selected.length} sản phẩm</Typography.Text>
            <Button icon={<CheckOutlined />} onClick={() => void approveSelected()}>
              Duyệt đã chọn
            </Button>
            <Popconfirm
              title={`Xoá ${selected.length} sản phẩm đã chọn?`}
              description="Các sản phẩm này cũng được gỡ khỏi các video đang gắn."
              okText="Xoá"
              cancelText="Huỷ"
              okButtonProps={{ danger: true }}
              onConfirm={deleteSelected}
            >
              <Button danger icon={<DeleteOutlined />}>
                Xoá đã chọn
              </Button>
            </Popconfirm>
            <Button type="link" onClick={() => setTicked([])}>
              Bỏ chọn
            </Button>
          </Flex>
        )}
        <Card styles={{ body: { padding: 0 } }}>
          <Table<AffiliateProduct>
            rowKey="id"
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setTicked(keys as number[]),
              getCheckboxProps: (product) => ({ "aria-label": `Chọn ${product.name}` }),
            }}
            columns={columns}
            dataSource={shown}
            loading={loading}
            pagination={{ pageSize: 50, hideOnSinglePage: true, showSizeChanger: false, ...tablePage }}
            scroll={{ x: 1100 }}
            locale={{
              emptyText: (
                <EmptyState
                  description={
                    products.length === 0
                      ? open
                        ? `Nhóm “${open.name}” chưa có sản phẩm nào`
                        : "Chưa có sản phẩm nào"
                      : whose === "mine" && mineCount === 0
                        ? "Bạn chưa thêm sản phẩm nào. Chọn “Cả đội” để xem của mọi người."
                        : "Không có sản phẩm nào khớp"
                  }
                  action={
                    products.length === 0 && (
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding("links")}>
                        Nhập sản phẩm đầu tiên
                      </Button>
                    )
                  }
                />
              ),
            }}
          />
        </Card>
      </div>
      <AddProductDrawer
        mode={adding}
        options={options}
        startTopicId={topicId}
        onClose={() => setAdding(null)}
        onManual={() => {
          setAdding(null);
          setTarget("new");
        }}
        onDone={async () => {
          await reload();
          loadOptions();
        }}
      />
      <ProductModal
        target={target}
        options={options}
        onClose={() => setTarget(null)}
        onDone={async () => {
          message.success("Đã lưu");
          setTarget(null);
          await reload();
          loadOptions();
        }}
      />
    </Flex>
  );
}
