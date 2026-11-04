"use client";

import {
  CheckOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateOptions, type AffiliateProduct } from "@/lib/api";
import ProductModal from "./ProductModal";
import StatusText from "@/components/StatusText";
import FilterSelect from "@/components/FilterSelect";

type Filters = { topicId?: number; status?: string; platform?: string; q: string };

/** The product list, best expected commission first. */
export default function Products() {
  const { message } = App.useApp();
  const [filters, setFilters] = useState<Filters>({ q: "" });
  const [options, setOptions] = useState<AffiliateOptions>({
    platforms: [],
    shop_types: { shopee: [], tiktok_shop: [] },
    topics: [],
  });
  const [products, setProducts] = useState<AffiliateProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<AffiliateProduct | "new" | null>(null);
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

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setProducts(await api<AffiliateProduct[]>(`/affiliate-products?${query}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [message, query]);

  useEffect(() => {
    const timer = setTimeout(reload, 250);
    return () => clearTimeout(timer);
  }, [reload]);

  useEffect(() => {
    // Without the lists the selects stay empty and the api still refuses unknown values.
    api<AffiliateOptions>("/affiliate-products/options").then(setOptions, () => undefined);
  }, []);

  async function act(run: () => Promise<unknown>, done: string) {
    try {
      await run();
      message.success(done);
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
            <a href={link} target="_blank" rel="noreferrer">
              {product.name}
            </a>
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
          <span>{product.shop_name}</span>
          <Typography.Text type="secondary">{product.shop_type_label}</Typography.Text>
        </Flex>
      ),
    },
    {
      title: "Sao / đã bán",
      key: "trust",
      width: 120,
      render: (_, product) => `${product.rating} / ${product.sold.toLocaleString("vi-VN")}`,
    },
    {
      title: "Giá",
      key: "price",
      width: 120,
      render: (_, product) => `${product.price.toLocaleString("vi-VN")}đ`,
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
      width: 230,
      render: (_, product) =>
        product.status === "approved" ? (
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
                disabled={product.problems.length > 0}
                onClick={() => act(() => api(`/affiliate-products/${product.id}/approve`, "POST"), "Đã duyệt")}
              >
                Duyệt
              </Button>
            </Tooltip>
          )}
          <Button aria-label={`Sửa ${product.name}`} icon={<EditOutlined />} onClick={() => setTarget(product)} />
          <Popconfirm
            title="Xoá sản phẩm này?"
            description="Sản phẩm cũng được gỡ khỏi các video đang gắn."
            okText="Xoá"
            cancelText="Huỷ"
            onConfirm={() => act(() => api(`/affiliate-products/${product.id}`, "DELETE"), "Đã xoá sản phẩm")}
          >
            <Button aria-label={`Xoá ${product.name}`} danger icon={<DeleteOutlined />} />
          </Popconfirm>
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setTarget("new")}>
            Thêm sản phẩm
          </Button>
        </Space>
      </Flex>
      <Card styles={{ body: { padding: 0 } }}>
        <Table<AffiliateProduct>
          rowKey="id"
          columns={columns}
          dataSource={products}
          loading={loading}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 1300 }}
          locale={{ emptyText: "Chưa có sản phẩm nào" }}
        />
      </Card>
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
