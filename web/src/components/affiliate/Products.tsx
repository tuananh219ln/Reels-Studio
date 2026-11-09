"use client";

import { useMe } from "@/components/MeContext";
import {
  CheckOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";
import AddProductDrawer, { type AddMode } from "./AddProductDrawer";
import ProductModal from "./ProductModal";
import QuickFill, { needsQuickFill } from "./QuickFill";
import StatusText from "@/components/StatusText";
import FilterSelect from "@/components/FilterSelect";

type Filters = { topicId?: number; status?: string; platform?: string; q: string };

/** The product list, best expected commission first. */
export default function Products() {
  const { message } = App.useApp();
  const { me } = useMe();
  const [filters, setFilters] = useState<Filters>({ q: "" });
  const [options, setOptions] = useState<AffiliateOptions>({
    platforms: [],
    shop_types: { shopee: [], tiktok_shop: [] },
    topics: [],
    shopee_lookup: false,
  });
  const [products, setProducts] = useState<AffiliateProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<AffiliateProduct | "new" | null>(null);
  const [adding, setAdding] = useState<AddMode | null>(null);
  // The rows ticked for "Xoá đã chọn"; only the ones still listed count, so a filter never deletes hidden rows.
  const [ticked, setTicked] = useState<number[]>([]);
  const { topicId, status, platform, q } = filters;

  const query = useMemo(() => {
    const params = new URLSearchParams();
    const values: [string, string | undefined][] = [
      ["topic_id", topicId?.toString()],
      ["status", status],
      ["platform", platform],
      ["q", q.trim()],
    ];
    for (const [name, value] of values) {
      if (value) {
        params.set(name, value);
      }
    }
    return params.toString();
  }, [topicId, status, platform, q]);

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

  const waiting = products.some((product) => product.lookup === "pending");
  useEffect(() => {
    // The worker reads a pasted link within seconds; the list follows it without a reload.
    if (!waiting) {
      return;
    }
    const timer = setInterval(() => void reload(true), 3000);
    return () => clearInterval(timer);
  }, [waiting, reload]);

  const loadOptions = useCallback(() => {
    // Without the lists the selects stay empty and the api still refuses unknown values.
    api<AffiliateOptions>("/affiliate-products/options").then(setOptions, () => undefined);
  }, []);

  useEffect(loadOptions, [loadOptions]);

  async function act(run: () => Promise<unknown>, done: string) {
    try {
      await run();
      message.success(done);
    } catch (err) {
      message.error(errorMessage(err));
    }
    await reload();
  }

  const listed = new Set(products.map((product) => product.id));
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
              <Typography.Text type="secondary">{product.topic}</Typography.Text>
            </Space>
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
      title: "Giá",
      key: "price",
      width: 120,
      render: (_, product) => (product.price > 0 ? `${product.price.toLocaleString("vi-VN")}đ` : "—"),
    },
    {
      title: "Hoa hồng ước tính",
      key: "commission",
      width: 150,
      render: (_, product) => (
        <Flex vertical gap={2}>
          <Typography.Text strong>{product.expected_commission.toLocaleString("vi-VN")}đ/đơn</Typography.Text>
          <Typography.Text type="secondary">{product.commission_rate}%</Typography.Text>
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
      render: (_, product) => (
        <Space wrap>
          {product.status === "approved" ? (
            <Button
              onClick={() => act(() => api(`/affiliate-products/${product.id}/unapprove`, "POST"), "Đã bỏ duyệt")}
            >
              Bỏ duyệt
            </Button>
          ) : (
            <Tooltip
              title={product.problems.length > 0 ? "Chưa đạt tiêu chí duyệt" : "Xem lại trang sản phẩm trước khi duyệt"}
            >
              <Button
                icon={<CheckOutlined />}
                disabled={product.problems.length > 0 || product.lookup === "pending"}
                onClick={() => act(() => api(`/affiliate-products/${product.id}/approve`, "POST"), "Đã duyệt")}
              >
                Duyệt
              </Button>
            </Tooltip>
          )}
          {product.lookup === "failed" && (
            <Tooltip title="Lấy lại thông tin từ Shopee">
              <Button
                aria-label={`Lấy lại thông tin ${product.name}`}
                icon={<ReloadOutlined />}
                onClick={() =>
                  act(() => api(`/affiliate-products/${product.id}/lookup`, "POST"), "Đang lấy lại thông tin")
                }
              />
            </Tooltip>
          )}
          <Button aria-label={`Sửa ${product.name}`} icon={<EditOutlined />} onClick={() => setTarget(product)} />
          {product.created_by_id === me.id && (
            <Popconfirm
              title="Xoá sản phẩm này?"
              description="Sản phẩm cũng được gỡ khỏi các video đang gắn."
              okText="Xoá"
              cancelText="Huỷ"
              onConfirm={() => act(() => api(`/affiliate-products/${product.id}`, "DELETE"), "Đã xoá sản phẩm")}
            >
              <Button aria-label={`Xoá ${product.name}`} danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <Flex wrap gap={12} justify="space-between" style={{ marginBottom: 16 }}>
        <Flex wrap gap={12}>
          <Input
            aria-label="Tìm theo sản phẩm hoặc shop"
            prefix={<SearchOutlined />}
            placeholder="Tìm theo sản phẩm hoặc shop"
            allowClear
            value={q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
            style={{ maxWidth: 280 }}
          />
          <FilterSelect
            aria-label="Lọc theo nhóm chủ đề"
            placeholder="Mọi nhóm chủ đề"
            value={topicId}
            onChange={(value) => setFilters({ ...filters, topicId: value })}
            options={options.topics.map((topic) => ({ value: topic.id, label: topic.name }))}
            style={{ width: 180 }}
          />
          <FilterSelect
            aria-label="Lọc theo nền tảng"
            placeholder="Mọi nền tảng"
            value={platform}
            onChange={(value) => setFilters({ ...filters, platform: value })}
            options={options.platforms}
            style={{ width: 160 }}
          />
          <FilterSelect
            aria-label="Lọc theo trạng thái"
            placeholder="Mọi trạng thái"
            value={status}
            onChange={(value) => setFilters({ ...filters, status: value })}
            options={[
              { value: "draft", label: "Nháp" },
              { value: "approved", label: "Đã duyệt" },
            ]}
            style={{ width: 160 }}
          />
        </Flex>
        <Space wrap>
          <Button icon={<DownloadOutlined />} href={`/api/affiliate-products/export.csv?${query}`}>
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
          dataSource={products}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 1330 }}
          locale={{ emptyText: "Chưa có sản phẩm nào" }}
        />
      </Card>
      <AddProductDrawer
        mode={adding}
        options={options}
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
        }}
      />
    </>
  );
}
