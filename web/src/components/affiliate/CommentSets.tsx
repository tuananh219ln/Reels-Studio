"use client";

import EmptyState from "@/components/EmptyState";
import FilterSelect from "@/components/FilterSelect";
import FormDrawer from "@/components/FormDrawer";
import StatusText from "@/components/StatusText";
import {
  api,
  errorMessage,
  formatDateTime,
  type AffGenerated,
  type AffiliateOptions,
  type AffSet,
  type AffSetProduct,
  type AffSetsTab,
  type AffSettings,
} from "@/lib/api";
import { useUrlId } from "@/lib/urlState";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Collapse,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";

/** At most this many products in a set (api aff_sets.MAX_ITEMS). */
const MAX_ITEMS = 10;
const pre: React.CSSProperties = { whiteSpace: "pre-wrap", fontSize: 13, margin: 0 };

/**
 * Affiliate → "Bộ bình luận": a Page's ready-made comments of up to 10 products each, which the Page writes under its
 * reels after the food comments (api aff_sets.py), its settings, and the short names, groups and tags of its group's
 * products.
 */
export default function CommentSets() {
  const { message } = App.useApp();
  const [pageId, setPageId] = useUrlId("page");
  const [pages, setPages] = useState<AffiliateOptions["pages"]>([]);
  const [tab, setTab] = useState<AffSetsTab | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<AffSet | "new" | null>(null);
  const [generating, setGenerating] = useState(false);
  const [setting, setSetting] = useState(false);
  const [previewing, setPreviewing] = useState<AffSet | null>(null);

  useEffect(() => {
    api<AffiliateOptions>("/affiliate-products/options").then(
      (options) => setPages(options.pages),
      () => undefined,
    );
  }, []);

  // A first visit opens on the member's own Page, the one they most likely look after.
  useEffect(() => {
    if (pageId === null && pages.length) setPageId((pages.find((page) => page.mine) ?? pages[0]).id);
  }, [pageId, pages, setPageId]);

  const reload = useCallback(async () => {
    if (pageId === null) return;
    setLoading(true);
    try {
      setTab(await api<AffSetsTab>(`/aff-sets?fanpage_id=${pageId}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [message, pageId]);

  useEffect(() => {
    const timer = setTimeout(() => void reload(), 0);
    return () => clearTimeout(timer);
  }, [reload]);

  async function run(work: () => Promise<unknown>, done?: string) {
    try {
      await work();
      if (done) message.success(done);
      await reload();
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
    }
  }

  const bodyOf = (one: AffSet, change: Partial<AffSet> = {}) => {
    const next = { ...one, ...change };
    return {
      name: next.name,
      intro_text: next.intro_text,
      outro_text: next.outro_text,
      tags: next.tags,
      enabled: next.enabled,
      priority: next.priority,
      product_ids: next.products.map((product) => product.id),
    };
  };

  const settings = tab?.settings;
  return (
    <Flex vertical gap={12} data-testid="comment-sets">
      <Flex gap={8} wrap align="center">
        <FilterSelect<number>
          aria-label="Chọn Page"
          placeholder="Chọn Page"
          value={pageId}
          style={{ width: 240 }}
          options={pages.map((page) => ({ value: page.id, label: page.name }))}
          onChange={(value) => setPageId(value ?? null)}
        />
        {settings && (
          <Typography.Text type="secondary">
            {settings.enabled ? (
              <StatusText tone="success">Bật</StatusText>
            ) : (
              <StatusText tone="warning">Tắt</StatusText>
            )}{" "}
            · {tab.sets.length} bộ · {settings.sets_per_post} bộ/bài · {settings.products_per_comment} link/bình luận
          </Typography.Text>
        )}
        <Space style={{ marginLeft: "auto" }} wrap>
          <Button icon={<ThunderboltOutlined />} disabled={!tab} onClick={() => setGenerating(true)}>
            Tạo tự động từ kho
          </Button>
          <Button icon={<PlusOutlined />} disabled={!tab} onClick={() => setEditing("new")}>
            Thêm bộ
          </Button>
          <Button icon={<SettingOutlined />} disabled={!tab} onClick={() => setSetting(true)}>
            Thiết lập
          </Button>
        </Space>
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Khi bài bật “Tự bình luận”, Page tự đăng {settings?.sets_per_post ?? 2} bộ dưới reel, sau bình luận ghim và các
        “Bình luận thêm”: bộ đầu chờ {minutes(settings?.first_delay)} phút sau bình luận món ăn cuối, các bộ sau cách
        nhau {minutes(settings?.delay)} phút. Facebook có thể ẩn bình luận nhiều link: nên thử 5 link/bình luận trước.
      </Typography.Text>

      {pageId === null ? (
        <EmptyState description="Chọn một Page để xem bộ bình luận của Page đó" />
      ) : tab && !tab.page.topic ? (
        <EmptyState description="Page chưa gắn nhóm chủ đề nên chưa có kho sản phẩm. Gắn nhóm ở Quản lý kênh." />
      ) : tab && tab.sets.length === 0 ? (
        <EmptyState
          description={`Page chưa có bộ bình luận nào. Kho nhóm “${tab.page.topic}” có ${tab.products.length} sản phẩm.`}
          action={
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => setGenerating(true)}>
              Tạo tự động từ kho
            </Button>
          }
        />
      ) : (
        <div
          style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}
          aria-busy={loading}
        >
          {tab?.sets.map((one) => (
            <Card
              key={one.id}
              size="small"
              data-testid="aff-set"
              title={one.name}
              extra={
                <Switch
                  size="small"
                  checked={one.enabled}
                  aria-label={`Bật ${one.name}`}
                  onChange={(enabled) => void run(() => api(`/aff-sets/${one.id}`, "PUT", bodyOf(one, { enabled })))}
                />
              }
              actions={[
                <Tooltip key="edit" title="Sửa">
                  <EditOutlined aria-label="Sửa" onClick={() => setEditing(one)} />
                </Tooltip>,
                <Tooltip key="copy" title="Nhân bản">
                  <CopyOutlined
                    aria-label="Nhân bản"
                    onClick={() => void run(() => api(`/aff-sets/${one.id}/duplicate`, "POST"), "Đã nhân bản")}
                  />
                </Tooltip>,
                <Tooltip key="view" title="Xem trước bình luận">
                  <EyeOutlined aria-label="Xem trước" onClick={() => setPreviewing(one)} />
                </Tooltip>,
                <Popconfirm
                  key="delete"
                  title="Xoá bộ này?"
                  description="Bình luận đã đăng vẫn ở trên Facebook."
                  okText="Xoá"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => run(() => api(`/aff-sets/${one.id}`, "DELETE"), "Đã xoá")}
                >
                  <DeleteOutlined aria-label="Xoá" />
                </Popconfirm>,
              ]}
            >
              <Flex vertical gap={4}>
                <span>
                  {one.valid_count < one.products.length ? (
                    <StatusText tone="warning">
                      {one.valid_count}/{one.products.length} hợp lệ
                    </StatusText>
                  ) : (
                    `${one.products.length}/${MAX_ITEMS} sản phẩm`
                  )}{" "}
                  · ưu tiên {one.priority}
                </span>
                {one.tags.length > 0 && (
                  <div>
                    {one.tags.map((tag) => (
                      <Tag key={tag}>{tag}</Tag>
                    ))}
                  </div>
                )}
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {one.last_used_at
                    ? `Dùng ${one.use_count} lần · gần nhất ${formatDateTime(one.last_used_at)}`
                    : "Chưa dùng"}
                </Typography.Text>
                {one.warnings.map((warning) => (
                  <StatusText key={warning} tone="warning">
                    {warning}
                  </StatusText>
                ))}
              </Flex>
            </Card>
          ))}
        </div>
      )}

      {tab && tab.products.length > 0 && (
        <Collapse
          items={[
            {
              key: "products",
              label: `Tên ngắn, nhóm, tags của ${tab.products.length} sản phẩm trong kho`,
              children: <ProductLabels products={tab.products} onSaved={reload} />,
            },
          ]}
        />
      )}

      {tab && (
        <>
          <SetDrawer
            key={editing === null ? "closed" : editing === "new" ? "new" : editing.id}
            target={editing}
            products={tab.products}
            onClose={() => setEditing(null)}
            onSave={async (body) => {
              const ok = await run(
                () =>
                  editing === "new"
                    ? api("/aff-sets", "POST", { ...body, fanpage_id: tab.page.id })
                    : api(`/aff-sets/${(editing as AffSet).id}`, "PUT", body),
                "Đã lưu bộ bình luận",
              );
              if (ok) setEditing(null);
            }}
          />
          <GenerateDrawer
            key={generating ? "open" : "closed"}
            open={generating}
            tab={tab}
            onClose={() => setGenerating(false)}
            onDone={() => {
              setGenerating(false);
              void reload();
            }}
          />
          <SettingsDrawer
            open={setting}
            tab={tab}
            onClose={() => setSetting(false)}
            onSave={async (next) => {
              const ok = await run(() => api(`/aff-sets/settings/${tab.page.id}`, "PUT", next), "Đã lưu thiết lập");
              if (ok) setSetting(false);
            }}
          />
        </>
      )}
      <Modal title={previewing?.name} open={previewing !== null} footer={null} onCancel={() => setPreviewing(null)}>
        <pre style={pre}>{previewing?.preview || "Chưa có sản phẩm hợp lệ"}</pre>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Link thật do tài khoản Shopee của Page tạo riêng cho từng video khi đăng.
        </Typography.Text>
      </Modal>
    </Flex>
  );
}

function minutes(span?: [number, number]) {
  if (!span) return "…";
  const [low, high] = span.map((seconds) => Math.round((seconds / 60) * 10) / 10);
  return low === high ? `${low}` : `${low}–${high}`;
}

type SetBody = {
  name: string;
  intro_text: string;
  outro_text: string;
  tags: string[];
  enabled: boolean;
  priority: number;
  product_ids: number[];
};

/** "Thêm bộ" / "Sửa": the set's lines and its products in order, picked from the Page's stock. */
function SetDrawer({
  target,
  products,
  onClose,
  onSave,
}: {
  target: AffSet | "new" | null;
  products: AffSetProduct[];
  onClose: () => void;
  onSave: (body: SetBody) => Promise<void>;
}) {
  const [form] = Form.useForm();
  // The drawer is mounted again for each set (its `key`), so the state starts from the set opened.
  const one = target === "new" || target === null ? null : target;
  const [ids, setIds] = useState<number[]>(() => one?.products.map((product) => product.id) ?? []);
  const [category, setCategory] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const initialValues = {
    name: one?.name ?? "",
    intro_text: one?.intro_text ?? "",
    outro_text: one?.outro_text ?? "",
    tags: one?.tags ?? [],
    enabled: one?.enabled ?? true,
    priority: one?.priority ?? 3,
  };

  const byId = new Map(products.map((product) => [product.id, product]));
  const categories = [...new Set(products.map((product) => product.category).filter(Boolean))] as string[];
  const choices = products.filter(
    (product) => !ids.includes(product.id) && (category === null || product.category === category),
  );
  const move = (place: number, by: number) => {
    const next = [...ids];
    [next[place], next[place + by]] = [next[place + by], next[place]];
    setIds(next);
  };

  async function save() {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await onSave({ ...values, product_ids: ids });
    } finally {
      setSaving(false);
    }
  }

  return (
    <FormDrawer
      title={target === "new" ? "Thêm bộ bình luận" : "Sửa bộ bình luận"}
      open={target !== null}
      onClose={onClose}
      onOk={save}
      okText="Lưu"
      confirmLoading={saving}
      guard={form}
      width={600}
    >
      <Form form={form} layout="vertical" initialValues={initialValues}>
        <Form.Item name="name" label="Tên bộ (nội bộ)" rules={[{ required: true, message: "Nhập tên bộ" }]}>
          <Input maxLength={120} placeholder="Bộ 03 – Hạt & ngũ cốc" />
        </Form.Item>
        <Form.Item name="intro_text" label="Câu mở đầu">
          <Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} maxLength={1000} />
        </Form.Item>
        <Form.Item label={`Sản phẩm (${ids.length}/${MAX_ITEMS})`} required>
          <Flex vertical gap={6}>
            <Flex gap={6}>
              <Select
                allowClear
                placeholder="Mọi nhóm"
                style={{ width: 140 }}
                value={category}
                options={categories.map((name) => ({ value: name, label: name }))}
                onChange={(value) => setCategory(value ?? null)}
              />
              <Select
                showSearch
                aria-label="Thêm sản phẩm"
                placeholder={ids.length >= MAX_ITEMS ? `Đã đủ ${MAX_ITEMS} sản phẩm` : "Tìm sản phẩm để thêm"}
                disabled={ids.length >= MAX_ITEMS}
                style={{ flex: 1 }}
                value={null}
                optionFilterProp="label"
                options={choices.map((product) => ({
                  value: product.id,
                  label: product.short_name || product.name,
                  disabled: !product.usable,
                }))}
                onChange={(value: number | null) => value !== null && setIds([...ids, value])}
              />
            </Flex>
            {ids.map((id, place) => {
              const product = byId.get(id);
              return (
                <Flex key={id} gap={4} align="center">
                  <Typography.Text style={{ width: 24 }}>{place + 1}.</Typography.Text>
                  <Typography.Text ellipsis style={{ flex: 1 }} type={product?.usable ? undefined : "warning"}>
                    {product ? product.short_name || product.name : `Sản phẩm #${id}`}
                    {product && !product.usable && " (không dùng được)"}
                  </Typography.Text>
                  <Button
                    size="small"
                    type="text"
                    icon={<ArrowUpOutlined />}
                    aria-label="Lên"
                    disabled={place === 0}
                    onClick={() => move(place, -1)}
                  />
                  <Button
                    size="small"
                    type="text"
                    icon={<ArrowDownOutlined />}
                    aria-label="Xuống"
                    disabled={place === ids.length - 1}
                    onClick={() => move(place, 1)}
                  />
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<CloseOutlined />}
                    aria-label="Bỏ"
                    onClick={() => setIds(ids.filter((other) => other !== id))}
                  />
                </Flex>
              );
            })}
          </Flex>
        </Form.Item>
        <Form.Item name="outro_text" label="Câu kết (tuỳ chọn)">
          <Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} maxLength={1000} />
        </Form.Item>
        <Form.Item
          name="tags"
          label="Tags (chủ đề video hợp với bộ)"
          extra="Gõ rồi Enter. Tag của sản phẩm cũng được tính."
        >
          <Select mode="tags" tokenSeparators={[",", ";"]} open={false} />
        </Form.Item>
        <Flex gap={24}>
          <Form.Item name="priority" label="Ưu tiên (1–5)">
            <InputNumber min={1} max={5} />
          </Form.Item>
          <Form.Item name="enabled" label="Dùng bộ này" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Flex>
      </Form>
    </FormDrawer>
  );
}

/** "Tạo tự động từ kho": cut the usable products of the Page's group into sets, preview, then make them. */
function GenerateDrawer({
  open,
  tab,
  onClose,
  onDone,
}: {
  open: boolean;
  tab: AffSetsTab;
  onClose: () => void;
  onDone: () => void;
}) {
  const { message } = App.useApp();
  const [split, setSplit] = useState("by_category");
  const [perSet, setPerSet] = useState(MAX_ITEMS);
  const [withOutro, setWithOutro] = useState(true);
  const [preview, setPreview] = useState<AffGenerated | null>(null);
  const [busy, setBusy] = useState(false);
  const body = { fanpage_id: tab.page.id, split, per_set: perSet, with_outro: withOutro };

  // A changed choice needs a new preview before anything is made.
  const changed =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value);
      setPreview(null);
    };

  async function send(dryRun: boolean) {
    setBusy(true);
    try {
      const answer = await api<AffGenerated>("/aff-sets/generate", "POST", { ...body, dry_run: dryRun });
      if (dryRun) {
        setPreview(answer);
      } else {
        message.success(`Đã tạo ${answer.created} bộ`);
        onDone();
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Tạo tự động từ kho"
      open={open}
      onClose={onClose}
      width={600}
      footer={
        <Flex gap={8} justify="flex-end">
          <Button onClick={onClose}>Huỷ</Button>
          <Button loading={busy} onClick={() => void send(true)}>
            Xem trước
          </Button>
          <Button type="primary" loading={busy} disabled={!preview?.sets.length} onClick={() => void send(false)}>
            {preview ? `Tạo ${preview.sets.length} bộ` : "Tạo"}
          </Button>
        </Flex>
      }
    >
      <Flex vertical gap={12}>
        <Typography.Text type="secondary">
          Lấy các sản phẩm Shopee đã duyệt của nhóm “{tab.page.topic}”, mỗi bộ một câu mở đầu khác nhau để bình luận
          không giống hệt nhau. Sản phẩm chưa có nhóm xếp vào “Khác”.
        </Typography.Text>
        <Segmented
          value={split}
          onChange={(value) => changed(setSplit)(String(value))}
          options={tab.splits.map((one) => ({ value: one.value, label: one.label }))}
        />
        <Space>
          <span>Số sản phẩm mỗi bộ</span>
          <InputNumber
            min={1}
            max={MAX_ITEMS}
            value={perSet}
            onChange={(value) => changed(setPerSet)(value ?? MAX_ITEMS)}
          />
          <Switch checked={withOutro} onChange={changed(setWithOutro)} />{" "}
          <span>Thêm câu kết “giá có thể thay đổi”</span>
        </Space>
        {preview?.sets.map((one) => (
          <Card key={one.name} size="small" title={one.name}>
            <Typography.Text type="secondary">{one.intro_text}</Typography.Text>
            <ol style={{ margin: "4px 0 0", paddingLeft: 20 }}>
              {one.products.map((name, place) => (
                <li key={place}>{name}</li>
              ))}
            </ol>
          </Card>
        ))}
      </Flex>
    </FormDrawer>
  );
}

/** "Thiết lập": the Page's settings for its set comments (delays typed in minutes, kept in seconds). */
function SettingsDrawer({
  open,
  tab,
  onClose,
  onSave,
}: {
  open: boolean;
  tab: AffSetsTab;
  onClose: () => void;
  onSave: (next: AffSettings) => Promise<void>;
}) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const lineFormat = Form.useWatch("line_format", form) as string | undefined;

  useEffect(() => {
    if (!open) return;
    const { first_delay, delay, ...rest } = tab.settings;
    form.setFieldsValue({
      ...rest,
      first_min: first_delay[0] / 60,
      first_max: first_delay[1] / 60,
      delay_min: delay[0] / 60,
      delay_max: delay[1] / 60,
    });
  }, [open, tab.settings, form]);

  async function save() {
    const { first_min, first_max, delay_min, delay_max, ...rest } = await form.validateFields();
    setSaving(true);
    try {
      await onSave({
        ...rest,
        first_delay: [Math.round(first_min * 60), Math.round(first_max * 60)],
        delay: [Math.round(delay_min * 60), Math.round(delay_max * 60)],
      });
    } finally {
      setSaving(false);
    }
  }

  const sample = (lineFormat ?? "")
    .replaceAll("{stt}", "1")
    .replaceAll("{short_name}", "Hạt chia Úc 500g")
    .replaceAll("{link}", "https://s.shopee.vn/xxxx");
  return (
    <FormDrawer
      title={`Thiết lập bình luận aff · ${tab.page.name}`}
      open={open}
      onClose={onClose}
      onOk={save}
      okText="Lưu"
      confirmLoading={saving}
      guard={form}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="enabled" label="Tự đăng bình luận aff cho Page này" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Flex gap={16}>
          <Form.Item name="sets_per_post" label="Số bộ mỗi bài">
            <InputNumber min={1} max={3} />
          </Form.Item>
          <Form.Item name="products_per_comment" label="Link mỗi bình luận">
            <InputNumber min={1} max={MAX_ITEMS} />
          </Form.Item>
          <Form.Item name="no_repeat_days" label="Không lặp bộ trong (ngày)">
            <InputNumber min={0} max={30} />
          </Form.Item>
        </Flex>
        <Form.Item name="strategy" label="Cách chọn bộ">
          <Select options={tab.strategies} />
        </Form.Item>
        <Form.Item label="Chờ sau bình luận món ăn cuối (phút)">
          <Space>
            <Form.Item name="first_min" noStyle>
              <InputNumber min={0} max={60} step={1} aria-label="Ít nhất" />
            </Form.Item>
            –
            <Form.Item name="first_max" noStyle>
              <InputNumber min={0} max={60} step={1} aria-label="Nhiều nhất" />
            </Form.Item>
          </Space>
        </Form.Item>
        <Form.Item label="Nghỉ giữa các bình luận aff (phút)">
          <Space>
            <Form.Item name="delay_min" noStyle>
              <InputNumber min={0.5} max={60} step={1} aria-label="Ít nhất" />
            </Form.Item>
            –
            <Form.Item name="delay_max" noStyle>
              <InputNumber min={0.5} max={60} step={1} aria-label="Nhiều nhất" />
            </Form.Item>
          </Space>
        </Form.Item>
        <Form.Item
          name="line_format"
          label="Mẫu một dòng sản phẩm"
          extra={`Biến: {stt}, {short_name}, {link}. Ví dụ: ${sample}`}
          rules={[{ required: true, pattern: /\{link\}/, message: "Mẫu phải có {link}" }]}
        >
          <Input maxLength={200} />
        </Form.Item>
      </Form>
    </FormDrawer>
  );
}

/** The short name, group and tags of each product of the Page's group, edited in place (the approval stays). */
function ProductLabels({ products, onSaved }: { products: AffSetProduct[]; onSaved: () => void }) {
  const { message } = App.useApp();
  async function save(product: AffSetProduct, change: Partial<AffSetProduct>) {
    const next = { ...product, ...change };
    try {
      await api(`/aff-sets/products/${product.id}`, "PATCH", {
        short_name: next.short_name,
        category: next.category,
        tags: next.tags,
      });
      onSaved();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }
  return (
    <Table<AffSetProduct>
      size="small"
      rowKey="id"
      dataSource={products}
      pagination={{ pageSize: 20, hideOnSinglePage: true }}
      scroll={{ x: 720 }}
      columns={[
        {
          title: "Sản phẩm",
          dataIndex: "name",
          render: (name: string, product) => (
            <Flex vertical>
              <Typography.Text ellipsis style={{ maxWidth: 260 }}>
                {name}
              </Typography.Text>
              {!product.usable && (
                <StatusText tone="warning">Không dùng được (chưa duyệt hoặc không có link)</StatusText>
              )}
            </Flex>
          ),
        },
        {
          title: "Tên ngắn",
          dataIndex: "short_name",
          width: 200,
          render: (value: string | null, product) => (
            <Input
              size="small"
              maxLength={60}
              defaultValue={value ?? ""}
              placeholder={product.name.slice(0, 30)}
              aria-label={`Tên ngắn của ${product.name}`}
              onBlur={(event) =>
                event.target.value.trim() !== (value ?? "") && void save(product, { short_name: event.target.value })
              }
            />
          ),
        },
        {
          title: "Nhóm",
          dataIndex: "category",
          width: 130,
          render: (value: string | null, product) => (
            <Input
              size="small"
              maxLength={60}
              defaultValue={value ?? ""}
              aria-label={`Nhóm của ${product.name}`}
              onBlur={(event) =>
                event.target.value.trim() !== (value ?? "") && void save(product, { category: event.target.value })
              }
            />
          ),
        },
        {
          title: "Tags",
          dataIndex: "tags",
          width: 220,
          render: (tags: string[], product) => (
            <Select
              size="small"
              mode="tags"
              open={false}
              tokenSeparators={[",", ";"]}
              style={{ width: "100%" }}
              defaultValue={tags}
              aria-label={`Tags của ${product.name}`}
              onChange={(next: string[]) => void save(product, { tags: next })}
            />
          ),
        },
        { title: "Số bộ", dataIndex: "set_count", width: 70 },
      ]}
    />
  );
}
