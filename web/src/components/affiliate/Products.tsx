"use client";
import ProductActions from "@/components/actions/ProductActions";

import EmptyState from "@/components/EmptyState";
import FilterSelect from "@/components/FilterSelect";
import { useMe } from "@/components/MeContext";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatDateTime, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";
import { useUrlChoice, useUrlId, useUrlPage } from "@/lib/urlState";
import {
  AppstoreOutlined,
  BarsOutlined,
  CheckOutlined,
  DeleteOutlined,
  DownOutlined,
  DownloadOutlined,
  FacebookFilled,
  LoadingOutlined,
  PlusOutlined,
  SearchOutlined,
  ShoppingOutlined,
  SwapOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  App,
  Avatar,
  Button,
  Card,
  Checkbox,
  Dropdown,
  Flex,
  Input,
  Popconfirm,
  Progress,
  Segmented,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import AddProductDrawer, { type AddMode } from "./AddProductDrawer";
import CustomLinkExport from "./CustomLinkExport";
import CustomLinkImport from "./CustomLinkImport";
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

/** The four steps a product goes through, one column each on the board: drafts short on stars or sales, drafts ready to
 * approve, approved Shopee products with no affiliate link yet (what Custom Link converts), and ready to use. */
type Lane = "fill" | "waiting" | "link" | "ready";

function laneOf(product: AffiliateProduct): Lane {
  if (product.status !== "approved") return product.short_on_counts ? "fill" : "waiting";
  return product.platform === "shopee" && !product.url ? "link" : "ready";
}

const LANES: { value: Lane; title: string; hint: string }[] = [
  { value: "fill", title: "1 · Cần điền", hint: "Điền sao, lượt bán ngay trên thẻ rồi duyệt" },
  { value: "waiting", title: "2 · Chờ duyệt", hint: "Đạt tiêu chí, chờ một người duyệt" },
  { value: "link", title: "3 · Cần link", hint: "Đã duyệt nhưng chưa có link affiliate" },
  { value: "ready", title: "4 · Sẵn sàng", hint: "Dùng được trong video và bộ bình luận" },
];
const LANE_CARDS = 5; // cards a column shows before "Xem thêm"

const VIEW_KEY = "affiliate-products-view";
const viewListeners = new Set<() => void>();
let chosenView: "board" | "table" | null = null; // kept when the browser refuses storage
function readView(): "board" | "table" {
  if (chosenView) return chosenView;
  try {
    return window.localStorage.getItem(VIEW_KEY) === "board" ? "board" : "table";
  } catch {
    return "table";
  }
}
function writeView(next: "board" | "table") {
  chosenView = next;
  try {
    window.localStorage.setItem(VIEW_KEY, next);
  } catch {
    // Not remembered across visits; the choice still holds for this one.
  }
  viewListeners.forEach((listener) => listener());
}
function subscribeView(listener: () => void) {
  viewListeners.add(listener);
  return () => void viewListeners.delete(listener);
}

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
  const [stage, setStage] = useUrlChoice<Stage>("stage", "all", ["fill", "waiting", "approved"]);
  // The rows ticked for "Xoá đã chọn"; only the ones still listed count, so a filter never deletes hidden rows.
  const [ticked, setTicked] = useState<number[]>([]);
  // "Nhập / Xuất" opens these two; "Chưa có link" narrows the list to what Custom Link still has to convert.
  const [customLink, setCustomLink] = useState<"export" | "import" | null>(null);
  const [noLink, setNoLink] = useState(false);
  // The table is the default; the member's choice of the board is remembered in this browser.
  const view = useSyncExternalStore(subscribeView, readView, () => "table" as const);
  const [expanded, setExpanded] = useState<Lane[]>([]);
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

  // The whole list of the group: new rows are only the group maker's, so there is no "Tôi thêm / Cả đội" here (decision
  // 2026-11-25); each row says who added it.
  const allRows = products;
  const stageCounts = Object.fromEntries(
    STAGES.map(({ value }) => [
      value,
      value === "all" ? allRows.length : allRows.filter((product) => stageOf(product) === value).length,
    ]),
  ) as Record<Stage, number>;
  const staged = stage === "all" ? allRows : allRows.filter((product) => stageOf(product) === stage);
  const shown = noLink ? staged.filter((product) => !product.url) : staged;
  const withoutLink = allRows.filter((product) => !product.url).length;
  // "Xuất CSV" follows the group, platform and search, and the stage as far as the api knows it (draft or approved).
  const exportQuery = [query, stage === "approved" ? "status=approved" : stage === "all" ? "" : "status=draft"]
    .filter(Boolean)
    .join("&");
  const open = options.topics.find((topic) => topic.id === topicId);
  const pagesOf = (id: number) => options.pages.filter((page) => page.knowledge_topic_id === id);

  const listed = new Set(shown.map((product) => product.id));
  const selected = ticked.filter((id) => listed.has(id));

  async function approveSelected() {
    await approveIds(selected);
  }

  async function approveIds(ids: number[]) {
    try {
      const { approved, skipped } = await api<{ approved: number; skipped: number }>(
        "/affiliate-products/approve",
        "POST",
        { product_ids: ids },
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
      width: 420,
      render: (_, product) => {
        const link = product.url ?? product.page_url ?? undefined;
        return (
          <Flex gap={10} align="flex-start">
            <Avatar
              shape="square"
              size={44}
              src={product.image_url ?? undefined}
              icon={<ShoppingOutlined />}
              style={{ flex: "none" }}
            />
            <Flex vertical gap={2} style={{ minWidth: 0 }}>
              <a
                href={link}
                target="_blank"
                rel="noreferrer"
                style={{
                  wordBreak: "break-word",
                  fontWeight: 600,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {product.name}
              </a>
              {product.lookup === "pending" && (
                <Typography.Text type="secondary">
                  <LoadingOutlined /> Đang lấy thông tin từ Shopee…
                </Typography.Text>
              )}
              {product.lookup === "failed" && <Typography.Text type="danger">{product.lookup_error}</Typography.Text>}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {[product.shop_name, product.shop_type_label].filter(Boolean).join(" · ") || "—"}
              </Typography.Text>
              <Space size={4} wrap>
                <Tag bordered={false} style={{ margin: 0 }}>
                  {product.platform_label}
                </Tag>
                {product.from_shopee_api && (
                  <Tag bordered={false} style={{ margin: 0 }}>
                    Tìm qua API
                  </Tag>
                )}
                {topicId === undefined && <Typography.Text type="secondary">{product.topic}</Typography.Text>}
              </Space>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <Tooltip title="Link lưu sẵn của sản phẩm được dùng trong bình luận khi Page đăng bài chưa có tài khoản Shopee dùng được.">
                  <span>Người thêm: {product.created_by_id === me.id ? "bạn" : product.created_by}</span>
                </Tooltip>
                {product.video_count > 0 && `, ${product.video_count} video`}
              </Typography.Text>
            </Flex>
          </Flex>
        );
      },
    },
    {
      title: "Sao / đã bán",
      key: "trust",
      width: 110,
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
      width: 240,
      render: (_, product) =>
        product.lookup === "pending" ? (
          <StatusText tone="idle">Đang lấy thông tin</StatusText>
        ) : product.status === "approved" ? (
          <Flex vertical gap={2} align="flex-start">
            <StatusText tone="success">Đã duyệt</StatusText>
            {product.checked_at && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
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
      title: "Link",
      key: "link",
      width: 130,
      render: (_, product) =>
        product.url ? (
          <Space size={4}>
            <Tag color="success" bordered={false} style={{ margin: 0 }}>
              Có link
            </Tag>
            <Typography.Text copyable={{ text: product.url, tooltips: ["Sao chép link", "Đã sao chép"] }} />
          </Space>
        ) : product.platform === "shopee" ? (
          <Tooltip title="Chưa có link lưu sẵn. Page có tài khoản Shopee riêng tự tạo link; còn lại dùng “Xuất file Custom Link” để chuyển đổi hàng loạt.">
            <Tag color="warning" bordered={false} style={{ margin: 0 }}>
              Chưa có link
            </Tag>
          </Tooltip>
        ) : (
          "—"
        ),
    },
    {
      title: "",
      key: "actions",
      width: 190,
      render: (_, product) => (
        <ProductActions product={product} onEdit={setTarget} onChanged={() => reload(true)} compact />
      ),
    },
  ];

  const myTopics = options.topics.filter((topic) => topic.mine);
  const otherTopics = options.topics.filter((topic) => !topic.mine);
  const topicOption = (topic: AffiliateOptions["topics"][number]) => ({
    value: topic.id,
    label: topic.name,
    count: topic.product_count,
    pages: pagesOf(topic.id).map((page) => page.name),
  });
  const topicOptions = [
    ...(myTopics.length > 0 ? [{ label: "Nhóm của tôi", options: myTopics.map(topicOption) }] : []),
    ...(otherTopics.length > 0
      ? [{ label: myTopics.length > 0 ? "Nhóm khác" : "Các nhóm", options: otherTopics.map(topicOption) }]
      : []),
  ];
  // Only the member who made a group adds products to it (decision 2026-11-25); with no group open, any group of mine.
  const canAdd = open ? open.can_add : options.topics.some((topic) => topic.can_add);
  const cannotAdd = open
    ? `Chỉ người tạo nhóm “${open.name}” mới thêm được sản phẩm`
    : "Bạn chưa có nhóm nào để thêm sản phẩm";
  const importExport = [
    {
      key: "file",
      icon: <UploadOutlined />,
      label: "Nhập file (Lấy link hàng loạt)",
      disabled: !canAdd,
      title: canAdd ? undefined : cannotAdd,
      onClick: () => setAdding("file"),
    },
    {
      key: "csv",
      icon: <DownloadOutlined />,
      label: <a href={`/api/affiliate-products/export.csv?${exportQuery}`}>Xuất CSV</a>,
    },
  ];

  const lanes = Object.fromEntries(LANES.map(({ value }) => [value, [] as AffiliateProduct[]])) as Record<
    Lane,
    AffiliateProduct[]
  >;
  for (const product of allRows) lanes[laneOf(product)].push(product);
  const mineToLink = lanes.link.filter((product) => product.created_by_id === me.id).length;
  const needsGroup = "Chọn một nhóm chủ đề ở trên trước";

  /** The button at the head of a column: the one bulk step that column has. */
  function laneAction(lane: Lane) {
    if (lane === "waiting" && lanes.waiting.length > 0) {
      return (
        <Button
          icon={<CheckOutlined />}
          block
          onClick={() => void approveIds(lanes.waiting.slice(0, 500).map((product) => product.id))}
        >
          Duyệt tất cả ({lanes.waiting.length})
        </Button>
      );
    }
    if (lane === "link" && lanes.link.length > 0) {
      return (
        <Flex vertical gap={6}>
          <Tooltip
            title={topicId === undefined ? needsGroup : mineToLink === 0 ? "Không có món nào của bạn" : undefined}
          >
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              block
              disabled={topicId === undefined || mineToLink === 0}
              onClick={() => setCustomLink("export")}
            >
              Xuất file Custom Link ({mineToLink})
            </Button>
          </Tooltip>
          <Tooltip title={topicId === undefined ? needsGroup : undefined}>
            <Button
              icon={<UploadOutlined />}
              block
              disabled={topicId === undefined}
              onClick={() => setCustomLink("import")}
            >
              Nhập kết quả Shopee
            </Button>
          </Tooltip>
        </Flex>
      );
    }
    return null;
  }

  function card(product: AffiliateProduct, lane: Lane) {
    return (
      <Card key={product.id} size="small" styles={{ body: { padding: 8 } }} data-testid="product-card">
        <Flex gap={8} align="flex-start">
          <Avatar
            shape="square"
            size={36}
            src={product.image_url ?? undefined}
            icon={<ShoppingOutlined />}
            style={{ flex: "none" }}
          />
          <Flex vertical gap={2} style={{ minWidth: 0, flex: 1 }}>
            <a
              href={product.url ?? product.page_url ?? undefined}
              target="_blank"
              rel="noreferrer"
              style={{
                fontWeight: 600,
                fontSize: 13,
                wordBreak: "break-word",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {product.name}
            </a>
            {product.lookup === "pending" ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <LoadingOutlined /> Đang lấy thông tin từ Shopee…
              </Typography.Text>
            ) : (
              <Typography.Text style={{ fontSize: 12 }}>
                <Typography.Text strong type="success">
                  {product.expected_commission.toLocaleString("vi-VN")}đ/đơn
                </Typography.Text>{" "}
                <Typography.Text type="secondary">
                  · {product.rating} / {product.sold.toLocaleString("vi-VN")}
                </Typography.Text>
              </Typography.Text>
            )}
            {product.lookup === "failed" && (
              <Typography.Text type="danger" style={{ fontSize: 12 }}>
                {product.lookup_error}
              </Typography.Text>
            )}
            {product.problems.map((problem) => (
              <Typography.Text key={problem} type="warning" style={{ fontSize: 12 }}>
                {problem}
              </Typography.Text>
            ))}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {product.shop_name || "—"}
              {product.created_by_id !== me.id && ` · ${product.created_by}`}
              {topicId === undefined && ` · ${product.topic}`}
            </Typography.Text>
          </Flex>
        </Flex>
        {lane === "fill" && needsQuickFill(product) && (
          <div style={{ marginTop: 6 }}>
            <QuickFill product={product} options={options} onSaved={() => reload(true)} />
          </div>
        )}
        <div style={{ marginTop: 6 }}>
          <ProductActions product={product} onEdit={setTarget} onChanged={() => reload(true)} compact />
        </div>
      </Card>
    );
  }

  const ready = lanes.ready.length;
  const board = (
    <div
      data-testid="product-board"
      style={{
        display: "grid",
        gap: 12,
        gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
        alignItems: "start",
      }}
    >
      {LANES.map(({ value, title, hint }) => {
        const items = lanes[value];
        const all = expanded.includes(value);
        const shownItems = all ? items : items.slice(0, LANE_CARDS);
        const attention = value === "link" && items.length > 0;
        return (
          <Card
            key={value}
            size="small"
            data-testid={`lane-${value}`}
            style={attention ? { borderColor: "var(--ant-color-warning)" } : undefined}
            styles={{ body: { padding: 10 } }}
          >
            <Flex vertical gap={8}>
              <Flex justify="space-between" align="center">
                <Typography.Text strong>{title}</Typography.Text>
                <Tag
                  bordered={false}
                  color={items.length === 0 ? undefined : value === "ready" ? "success" : "warning"}
                  style={{ margin: 0 }}
                >
                  {items.length}
                </Tag>
              </Flex>
              {laneAction(value)}
              {items.length === 0 ? (
                <Typography.Text type="secondary" style={{ textAlign: "center", padding: "12px 0" }}>
                  {value === "ready" ? "Chưa có sản phẩm nào" : "✓ Đã sạch"}
                </Typography.Text>
              ) : (
                <>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {hint}
                  </Typography.Text>
                  {shownItems.map((product) => card(product, value))}
                  {items.length > LANE_CARDS && (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => setExpanded(all ? expanded.filter((x) => x !== value) : [...expanded, value])}
                    >
                      {all ? "Thu gọn" : `Xem thêm ${items.length - LANE_CARDS} món`}
                    </Button>
                  )}
                </>
              )}
            </Flex>
          </Card>
        );
      })}
    </div>
  );

  return (
    <Flex vertical gap={12}>
      <Flex wrap gap={8} align="center">
        <FilterSelect<number>
          aria-label="Lọc theo nhóm"
          data-testid="product-group"
          placeholder="Tất cả nhóm"
          value={topicId}
          onChange={(value) => {
            setFilters({ ...filters, topicId: value ?? undefined });
            setTicked([]);
          }}
          options={topicOptions}
          optionRender={(option) => (
            <Flex justify="space-between" gap={8}>
              <span>
                {option.label}
                {(option.data.pages as string[] | undefined)?.length ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {" "}
                    <FacebookFilled /> {(option.data.pages as string[]).join(", ")}
                  </Typography.Text>
                ) : null}
              </span>
              <Typography.Text type="secondary">{option.data.count as number}</Typography.Text>
            </Flex>
          )}
          style={{ width: 340, maxWidth: "100%", fontWeight: 600 }}
        />
        {open && (
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {pagesOf(open.id).length > 0
              ? `Dùng cho video của ${pagesOf(open.id).length} Page`
              : "Chưa Page nào đăng nhóm này"}
          </Typography.Text>
        )}
        <Space wrap style={{ marginLeft: "auto" }}>
          <Segmented<"board" | "table">
            aria-label="Cách xem sản phẩm"
            value={view}
            onChange={writeView}
            options={[
              { value: "board", label: "Quy trình", icon: <AppstoreOutlined /> },
              { value: "table", label: "Bảng", icon: <BarsOutlined /> },
            ]}
          />
          <Dropdown menu={{ items: importExport }} trigger={["click"]}>
            <Button icon={<SwapOutlined />}>
              Nhập / Xuất <DownOutlined />
            </Button>
          </Dropdown>
          <Tooltip title={canAdd ? undefined : cannotAdd}>
            <Button type="primary" icon={<PlusOutlined />} disabled={!canAdd} onClick={() => setAdding("links")}>
              Thêm sản phẩm
            </Button>
          </Tooltip>
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
        <FilterSelect
          aria-label="Lọc theo nền tảng"
          placeholder="Mọi nền tảng"
          value={platform}
          onChange={(value) => setFilters({ ...filters, platform: value })}
          options={options.platforms}
          style={{ width: 160 }}
        />
        {view === "table" && (
          <Checkbox checked={noLink} onChange={(event) => setNoLink(event.target.checked)}>
            Chưa có link ({withoutLink})
          </Checkbox>
        )}
      </Flex>
      <div data-testid="product-progress">
        <Flex justify="space-between" gap={8} wrap>
          <Typography.Text strong>
            {ready} / {allRows.length} sẵn sàng dùng trong bình luận
          </Typography.Text>
          <Typography.Text type={lanes.link.length > 0 ? "warning" : "secondary"}>
            {lanes.link.length > 0 ? `còn ${lanes.link.length} món chưa có link` : "mọi món đã duyệt đều có link"}
          </Typography.Text>
        </Flex>
        <Progress
          percent={allRows.length === 0 ? 0 : Math.round(((ready + lanes.link.length) / allRows.length) * 100)}
          success={{ percent: allRows.length === 0 ? 0 : Math.round((ready / allRows.length) * 100) }}
          showInfo={false}
          size="small"
          strokeColor="var(--ant-color-warning)"
        />
      </div>
      {view === "board" ? (
        loading && products.length === 0 ? null : allRows.length === 0 ? (
          <EmptyState
            description={
              products.length === 0
                ? open
                  ? `Nhóm “${open.name}” chưa có sản phẩm nào`
                  : "Chưa có sản phẩm nào"
                : "Không có sản phẩm nào khớp"
            }
            action={
              products.length === 0 &&
              canAdd && (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding("links")}>
                  Nhập sản phẩm đầu tiên
                </Button>
              )
            }
          />
        ) : (
          board
        )
      ) : (
        <>
          <div aria-label="Lọc theo trạng thái" role="group">
            {/* A filter, so it looks like one, not like a second row of the page's tabs. */}
            <Segmented<Stage>
              value={stage}
              onChange={setStage}
              options={STAGES.map(({ value, label }) => ({ value, label: `${label} (${stageCounts[value]})` }))}
            />
          </div>
          {selected.length > 0 && (
            <Flex gap={12} align="center" wrap data-testid="product-selection">
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
              scroll={{ x: 1150 }}
              locale={{
                emptyText: (
                  <EmptyState
                    description={
                      products.length === 0
                        ? open
                          ? `Nhóm “${open.name}” chưa có sản phẩm nào`
                          : "Chưa có sản phẩm nào"
                        : "Không có sản phẩm nào khớp"
                    }
                    action={
                      products.length === 0 &&
                      canAdd && (
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
        </>
      )}
      <CustomLinkExport
        open={customLink === "export"}
        onClose={() => setCustomLink(null)}
        topicId={topicId}
        topicName={open?.name}
        pages={topicId === undefined ? [] : pagesOf(topicId).map((page) => ({ id: page.id, name: page.name }))}
      />
      <CustomLinkImport
        open={customLink === "import"}
        onClose={() => setCustomLink(null)}
        topicId={topicId}
        onDone={() => reload(true)}
      />
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
