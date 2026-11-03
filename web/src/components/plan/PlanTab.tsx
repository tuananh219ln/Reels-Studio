"use client";

import {
  DeleteOutlined,
  ImportOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  VideoCameraAddOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import dayjs from "dayjs";
import "dayjs/locale/vi";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  errorMessage,
  upload,
  type Plan,
  type PlanIdeaFields,
  type PlanItem,
  type PlanItemStatus,
  type PlanPreview,
} from "@/lib/api";
import { usePolling } from "@/lib/polling";

const PLAN_DAYS = 30;
const MIN_PER_DAY = 3;
const MAX_PER_DAY = 5;
const JOB_POLL_MS = 3000;

export const PLAN_STATUS_COLORS: Record<PlanItemStatus, string> = {
  idea: "default",
  started: "processing",
  scripted: "blue",
  done: "success",
};

/** "Kế hoạch 30 ngày" of one topic group: 3-5 video ideas a day, imported, written by AI or typed in. */
export default function PlanTab({ topicId }: { topicId: number }) {
  const { message } = App.useApp();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [preview, setPreview] = useState<(PlanPreview & { fromAi: boolean }) | null>(null);
  const [adding, setAdding] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(
    async (quiet = false) => {
      try {
        const fresh = await api<Plan>(`/plans/${topicId}`);
        setPlan(fresh);
      } catch (err) {
        if (!quiet) {
          message.error(errorMessage(err));
        }
      }
    },
    [topicId, message],
  );

  useEffect(() => {
    api<Plan>(`/plans/${topicId}`)
      .then(setPlan)
      .catch((err) => message.error(errorMessage(err)));
  }, [topicId, message]);
  const working = plan?.job?.status === "queued" || plan?.job?.status === "running";
  // Only while "Tạo bằng AI" runs: the plan changes in the worker then, and nowhere else.
  usePolling(async () => (working ? reload(true) : undefined), JOB_POLL_MS);

  /** Every change answers with the whole plan. */
  async function change(call: () => Promise<Plan>, done?: string): Promise<boolean> {
    try {
      setPlan(await call());
      if (done) {
        message.success(done);
      }
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
    }
  }

  if (!plan) {
    return (
      <Flex justify="center" style={{ padding: 24 }}>
        <Spin />
      </Flex>
    );
  }

  const path = `/plans/${topicId}`;
  const byDay = (day: number) => plan.items.filter((item) => item.day === day);

  async function importFile(file: File) {
    setBusy(true);
    try {
      setPreview({ ...(await upload<PlanPreview>(`${path}/import`, file)), fromAi: false });
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function save(ideas: PlanIdeaFields[]) {
    if (await change(() => api<Plan>(`${path}/items`, "PUT", { ideas }), "Đã lưu kế hoạch")) {
      setPreview(null);
    }
  }

  return (
    <Flex vertical gap={16} data-testid="plan-tab">
      <Card size="small">
        <Flex wrap gap={16} align="center">
          <Flex align="center" gap={8}>
            <Typography.Text>Ngày bắt đầu</Typography.Text>
            <DatePicker
              aria-label="Ngày bắt đầu kế hoạch"
              format="DD/MM/YYYY"
              placeholder="Chọn ngày 1"
              value={plan.start_date ? dayjs(plan.start_date) : null}
              onChange={(value) =>
                change(() => api<Plan>(path, "PATCH", { start_date: value ? value.format("YYYY-MM-DD") : null }))
              }
            />
          </Flex>
          <Flex align="center" gap={8}>
            <Typography.Text>Số ý tưởng mỗi ngày</Typography.Text>
            <InputNumber
              aria-label="Số ý tưởng mỗi ngày"
              min={MIN_PER_DAY}
              max={MAX_PER_DAY}
              precision={0}
              value={plan.per_day}
              onChange={(value) => value && change(() => api<Plan>(path, "PATCH", { per_day: value }))}
              style={{ width: 72 }}
            />
          </Flex>
          <TodayLine plan={plan} />
          <Flex vertical style={{ minWidth: 200, marginLeft: "auto" }}>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Đã làm {plan.made}/{plan.items.length} ý tưởng
            </Typography.Text>
            <Progress
              percent={plan.items.length ? Math.round((plan.made / plan.items.length) * 100) : 0}
              size="small"
              showInfo={false}
            />
          </Flex>
        </Flex>
        <Flex wrap gap={8} style={{ marginTop: 12 }}>
          <Upload
            accept=".json,.csv,application/json,text/csv"
            showUploadList={false}
            beforeUpload={(file) => {
              void importFile(file);
              return false;
            }}
          >
            <Button icon={<ImportOutlined />} loading={busy}>
              Nhập file JSON/CSV
            </Button>
          </Upload>
          <Button
            icon={<RobotOutlined />}
            loading={working}
            onClick={() => change(() => api<Plan>(`${path}/generate`, "POST"))}
          >
            {working ? "AI đang lập kế hoạch…" : "Tạo bằng AI"}
          </Button>
        </Flex>
        <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 13 }}>
          File và kế hoạch AI đều hiện bảng xem trước; kế hoạch đang có chỉ bị thay khi bấm “Lưu kế hoạch”. AI lập 30
          ngày trong 3 lượt (mỗi lượt 10 ngày) với prompt kế hoạch bên dưới và mô hình đang chọn trong Cài đặt.
        </Typography.Paragraph>
        {plan.job?.status === "failed" && (
          <Alert
            type="error"
            showIcon
            style={{ marginTop: 12 }}
            title={`Tạo kế hoạch bằng AI bị lỗi: ${plan.job.error ?? ""}`}
          />
        )}
        {plan.draft && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 12 }}
            title={`AI đã lập xong ${plan.draft.ideas.length} ý tưởng, chưa lưu vào kế hoạch.`}
            action={
              <Flex gap={8}>
                <Button size="small" type="primary" onClick={() => setPreview({ ...plan.draft!, fromAi: true })}>
                  Xem trước
                </Button>
                <Button size="small" onClick={() => change(() => api<Plan>(`${path}/draft`, "DELETE"))}>
                  Bỏ
                </Button>
              </Flex>
            }
          />
        )}
      </Card>

      <PlanPromptCard
        plan={plan}
        onSave={(prompt) => change(() => api<Plan>(path, "PATCH", { prompt }), "Đã lưu prompt kế hoạch")}
      />

      <Row gutter={[12, 12]}>
        {Array.from({ length: PLAN_DAYS }, (_, index) => index + 1).map((day) => (
          <Col key={day} xs={24} md={12} xl={8}>
            <DayCard
              day={day}
              plan={plan}
              items={byDay(day)}
              onAdd={() => setAdding(day)}
              onMove={(itemId) => change(() => api<Plan>(`/plans/items/${itemId}`, "PATCH", { day }))}
              onChange={change}
            />
          </Col>
        ))}
      </Row>

      <AddIdeaModal
        day={adding}
        onClose={() => setAdding(null)}
        onAdd={async (idea) => {
          if (await change(() => api<Plan>(`${path}/items`, "POST", idea))) {
            setAdding(null);
          }
        }}
      />
      {preview && (
        <PreviewModal
          preview={preview}
          current={plan.items.length}
          onSave={() => save(preview.ideas)}
          onClose={() => setPreview(null)}
        />
      )}
    </Flex>
  );
}

function TodayLine({ plan }: { plan: Plan }) {
  if (plan.today_day === null) {
    return <Typography.Text type="secondary">Chọn ngày bắt đầu để app biết hôm nay là ngày mấy</Typography.Text>;
  }
  if (plan.today_day < 1) {
    return <Typography.Text type="secondary">Kế hoạch chưa bắt đầu</Typography.Text>;
  }
  if (plan.today_day > PLAN_DAYS) {
    return <Typography.Text type="secondary">Kế hoạch đã hết 30 ngày</Typography.Text>;
  }
  return (
    <Typography.Text strong data-testid="plan-today">
      Hôm nay là ngày {plan.today_day}/{PLAN_DAYS}
    </Typography.Text>
  );
}

function PlanPromptCard({ plan, onSave }: { plan: Plan; onSave: (prompt: string) => Promise<boolean> }) {
  const { modal } = App.useApp();
  const [value, setValue] = useState(plan.prompt);
  const [busy, setBusy] = useState(false);

  async function save(text: string) {
    setBusy(true);
    if (await onSave(text)) {
      setValue(text.trim());
    }
    setBusy(false);
  }

  return (
    <Collapse
      size="small"
      items={[
        {
          key: "prompt",
          label: "Prompt kế hoạch",
          children: (
            <>
              <Typography.Paragraph type="secondary">
                Chỗ điền <Typography.Text code>[Chủ đề nhóm]</Typography.Text> được thay bằng tên nhóm,{" "}
                <Typography.Text code>[Số video mỗi ngày]</Typography.Text> bằng số ý tưởng mỗi ngày; chỗ điền nào bị
                xóa thì được nối vào cuối prompt. Từ cấm của nhóm, ngày cuối tuần và định dạng JSON đầu ra do app tự
                thêm.
              </Typography.Paragraph>
              <Input.TextArea
                aria-label="Prompt kế hoạch"
                value={value}
                autoSize={{ minRows: 6, maxRows: 24 }}
                onChange={(event) => setValue(event.target.value)}
              />
              <Flex wrap gap={8} style={{ marginTop: 12 }}>
                <Button type="primary" loading={busy} disabled={!value.trim()} onClick={() => save(value)}>
                  Lưu
                </Button>
                <Button
                  disabled={busy}
                  onClick={() =>
                    modal.confirm({
                      title: "Khôi phục prompt kế hoạch mặc định?",
                      content: "Prompt đang dùng sẽ được thay bằng bản mặc định.",
                      okText: "Khôi phục",
                      cancelText: "Huỷ",
                      onOk: () => save(plan.default_prompt),
                    })
                  }
                >
                  Khôi phục mặc định
                </Button>
              </Flex>
            </>
          ),
        },
      ]}
    />
  );
}

function DayCard({
  day,
  plan,
  items,
  onAdd,
  onMove,
  onChange,
}: {
  day: number;
  plan: Plan;
  items: PlanItem[];
  onAdd: () => void;
  onMove: (itemId: number) => void;
  onChange: (call: () => Promise<Plan>) => Promise<boolean>;
}) {
  const [over, setOver] = useState(false);
  const date = plan.start_date
    ? dayjs(plan.start_date)
        .add(day - 1, "day")
        .locale("vi")
    : null;
  const today = plan.today_day === day;
  return (
    <Card
      size="small"
      data-testid={`plan-day-${day}`}
      title={
        <Flex align="center" gap={8}>
          <span>Ngày {day}</span>
          {date && (
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              {date.format("dddd, DD/MM")}
            </Typography.Text>
          )}
          {today && <Tag color="orange">Hôm nay</Tag>}
        </Flex>
      }
      extra={
        <Button
          size="small"
          type="text"
          icon={<PlusOutlined />}
          aria-label={`Thêm ý tưởng ngày ${day}`}
          disabled={items.length >= MAX_PER_DAY}
          onClick={onAdd}
        />
      }
      style={{ height: "100%", outline: over ? "2px dashed #fa8c16" : undefined }}
      // Dropping an idea dragged from another day moves it here, at the end.
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const id = Number(event.dataTransfer.getData("text/plan-item"));
        if (id && !items.some((item) => item.id === id)) {
          onMove(id);
        }
      }}
    >
      <Flex vertical gap={8}>
        {items.length === 0 && <Typography.Text type="secondary">Chưa có ý tưởng</Typography.Text>}
        {items.length > 0 && items.length < MIN_PER_DAY && (
          <Typography.Text type="warning" style={{ fontSize: 12 }}>
            Mới có {items.length} ý tưởng, nên có {MIN_PER_DAY}–{MAX_PER_DAY}
          </Typography.Text>
        )}
        {items.map((item) => (
          <IdeaCard key={item.id} item={item} onChange={onChange} />
        ))}
      </Flex>
    </Card>
  );
}

function IdeaCard({ item, onChange }: { item: PlanItem; onChange: (call: () => Promise<Plan>) => Promise<boolean> }) {
  const router = useRouter();
  const path = `/plans/items/${item.id}`;
  // Each field saves on its own when the edit ends (Enter or leaving the field).
  const edit = (field: keyof PlanIdeaFields, label: string) => ({
    tooltip: `Sửa ${label}`,
    onChange: (value: string) => {
      if (value !== item[field]) {
        void onChange(() => api<Plan>(path, "PATCH", { [field]: value }));
      }
    },
  });
  return (
    <div
      draggable
      onDragStart={(event) => event.dataTransfer.setData("text/plan-item", String(item.id))}
      data-testid="plan-idea"
      style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 8, cursor: "grab", background: "#fff" }}
    >
      <Flex justify="space-between" align="flex-start" gap={4}>
        <Typography.Paragraph strong editable={edit("topic", "chủ đề")} style={{ margin: 0, flex: 1 }}>
          {item.topic}
        </Typography.Paragraph>
        <Tag color={PLAN_STATUS_COLORS[item.status]} style={{ marginInlineEnd: 0 }}>
          {item.status_label}
        </Tag>
      </Flex>
      <Flex vertical gap={2} style={{ marginTop: 4, fontSize: 13 }}>
        <Typography.Text type="secondary" editable={edit("pain_group", "nhóm nỗi đau")}>
          {item.pain_group || "—"}
        </Typography.Text>
        <Typography.Paragraph editable={edit("pain", "nỗi đau")} style={{ margin: 0, fontSize: 13 }}>
          <Typography.Text type="secondary">Nỗi đau: </Typography.Text>
          {item.pain}
        </Typography.Paragraph>
        <Typography.Paragraph editable={edit("hook", "góc hook")} style={{ margin: 0, fontSize: 13 }}>
          <Typography.Text type="secondary">Hook: </Typography.Text>
          {item.hook}
        </Typography.Paragraph>
      </Flex>
      <Flex justify="space-between" align="center" style={{ marginTop: 6 }}>
        {item.video_id ? (
          <Link prefetch={false} href={`/videos/${item.video_id}`}>
            <PlayCircleOutlined /> Mở video
          </Link>
        ) : (
          <Button
            size="small"
            type="primary"
            ghost
            icon={<VideoCameraAddOutlined />}
            onClick={() => router.push(`/videos?plan_item=${item.id}`)}
          >
            Tạo video
          </Button>
        )}
        <Popconfirm
          title="Xoá ý tưởng này?"
          description={item.video_id ? "Video đã tạo từ ý tưởng vẫn được giữ." : undefined}
          okText="Xoá"
          cancelText="Huỷ"
          okButtonProps={{ danger: true }}
          onConfirm={() => onChange(() => api<Plan>(path, "DELETE"))}
        >
          <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="Xoá ý tưởng" />
        </Popconfirm>
      </Flex>
    </div>
  );
}

function AddIdeaModal({
  day,
  onClose,
  onAdd,
}: {
  day: number | null;
  onClose: () => void;
  onAdd: (idea: PlanIdeaFields) => Promise<void>;
}) {
  const [form] = Form.useForm<PlanIdeaFields>();
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      title={`Thêm ý tưởng ngày ${day ?? ""}`}
      open={day !== null}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Thêm"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={async (values) => {
          setBusy(true);
          await onAdd({ ...values, day: day ?? 1 });
          setBusy(false);
        }}
      >
        <Form.Item
          label="Chủ đề"
          name="topic"
          rules={[{ required: true, whitespace: true, message: "Hãy nhập chủ đề" }]}
          extra="Dùng làm Chủ đề khi tạo video"
        >
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} maxLength={300} />
        </Form.Item>
        <Form.Item label="Nhóm nỗi đau" name="pain_group">
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item label="Nỗi đau người xem" name="pain">
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} maxLength={1000} />
        </Form.Item>
        <Form.Item label="Góc hook" name="hook">
          <Input maxLength={500} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function PreviewModal({
  preview,
  current,
  onSave,
  onClose,
}: {
  preview: PlanPreview & { fromAi: boolean };
  current: number;
  onSave: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const blocked = preview.errors.length > 0 || preview.ideas.length === 0;
  return (
    <Modal
      open
      width={1000}
      title={preview.fromAi ? "Xem trước kế hoạch AI lập" : "Xem trước file nhập"}
      onCancel={onClose}
      okText="Lưu kế hoạch"
      cancelText={preview.fromAi ? "Để sau" : "Huỷ"}
      okButtonProps={{ disabled: blocked }}
      confirmLoading={busy}
      onOk={async () => {
        setBusy(true);
        await onSave();
        setBusy(false);
      }}
    >
      <Flex vertical gap={12}>
        {preview.errors.length > 0 && (
          <Alert
            type="error"
            showIcon
            title={`${preview.errors.length} lỗi, sửa file rồi nhập lại`}
            description={
              <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                {preview.errors.slice(0, 20).map((error) => (
                  <li key={error}>{error}</li>
                ))}
                {preview.errors.length > 20 && <li>… và {preview.errors.length - 20} lỗi khác</li>}
              </ul>
            }
          />
        )}
        {preview.warnings.map((warning) => (
          <Alert key={warning} type="warning" showIcon title={warning} />
        ))}
        <Typography.Text>
          {preview.ideas.length} ý tưởng.{" "}
          {current > 0 &&
            `Kế hoạch hiện có ${current} ý tưởng sẽ được thay; ý tưởng đã có video giữ liên kết nếu cùng chủ đề.`}
        </Typography.Text>
        <Table<PlanIdeaFields>
          size="small"
          rowKey={(row) => `${row.day}-${row.topic}`}
          dataSource={preview.ideas}
          pagination={{ pageSize: 40, hideOnSinglePage: true }}
          scroll={{ x: 900, y: 420 }}
          columns={[
            { title: "Ngày", dataIndex: "day", width: 64 },
            { title: "Chủ đề", dataIndex: "topic", width: 280 },
            { title: "Nhóm nỗi đau", dataIndex: "pain_group", width: 150 },
            { title: "Nỗi đau", dataIndex: "pain" },
            { title: "Góc hook", dataIndex: "hook", width: 220 },
          ]}
        />
      </Flex>
    </Modal>
  );
}
