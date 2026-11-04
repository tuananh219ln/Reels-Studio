"use client";

import {
  DeleteOutlined,
  DownOutlined,
  ImportOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  UpOutlined,
  VideoCameraAddOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Segmented,
  Select,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  theme,
} from "antd";
import dayjs from "dayjs";
import "dayjs/locale/vi";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import {
  api,
  errorMessage,
  formatDateTime,
  upload,
  type Plan,
  type PlanIdeaFields,
  type PlanItem,
  type PlanItemStatus,
  type PlanPost,
  type PlanPreview,
} from "@/lib/api";
import { usePolling } from "@/lib/polling";
import FormDrawer from "@/components/FormDrawer";
import { COLORS } from "@/app/theme";

const PLAN_DAYS = 30;
const MIN_PER_DAY = 3;
const MAX_PER_DAY = 5;
const JOB_POLL_MS = 3000;
const DRAG_TYPE = "text/plan-item";

export const PLAN_STATUS_COLORS: Record<PlanItemStatus, string> = {
  idea: "default",
  started: "processing",
  scripted: "blue",
  done: "success",
  scheduled: "purple",
  posted: "green",
};

/** The labels the api gives each status, in the order an idea goes through them, for the status filter. */
const STATUS_LABELS: Record<PlanItemStatus, string> = {
  idea: "Ý tưởng",
  started: "Đã tạo video",
  scripted: "Đã viết kịch bản",
  done: "Xong",
  scheduled: "Đã lên lịch",
  posted: "Đã đăng",
};

/** The colour a status Tag is drawn in, for the card's left border: the same palette as the Tag, none of its own. */
function statusColor(status: PlanItemStatus, token: ReturnType<typeof theme.useToken>["token"]): string {
  const byTag: Record<string, string> = {
    default: token.colorBorder,
    processing: token.colorInfo,
    blue: token.blue,
    success: token.colorSuccess,
    purple: token.purple,
    green: token.green,
  };
  return byTag[PLAN_STATUS_COLORS[status]];
}

/** Text compared without accents or case: "sau benh" finds "Sâu bệnh". */
export function searchKey(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}

type Filters = { status: PlanItemStatus | null; group: string | null; query: string };
const NO_FILTERS: Filters = { status: null, group: null, query: "" };

function matches(item: PlanItem, filters: Filters): boolean {
  const needle = searchKey(filters.query.trim());
  return (
    (!filters.status || item.status === filters.status) &&
    (!filters.group || item.pain_group === filters.group) &&
    (!needle || [item.topic, item.pain_group, item.pain, item.hook].some((text) => searchKey(text).includes(needle)))
  );
}

const COMPACT_KEY = "plan-compact";

/** "Đầy đủ | Gọn", remembered in this browser ("plan-compact"); full until chosen. */
function useCompact(): [boolean, (compact: boolean) => void] {
  // As useRememberedView (lib/view.ts) does for the video list.
  const [compact, setCompact] = useState(() => {
    try {
      return window.localStorage.getItem(COMPACT_KEY) === "compact";
    } catch {
      return false;
    }
  });
  return [
    compact,
    (value) => {
      setCompact(value);
      try {
        window.localStorage.setItem(COMPACT_KEY, value ? "compact" : "full");
      } catch {
        // Only a convenience: the choice then lasts until the page is left.
      }
    },
  ];
}

/** Ideas whose post is set or out: nothing is left to do for them. */
const FINISHED: PlanItemStatus[] = ["scheduled", "posted"];

type Change = (call: () => Promise<Plan>, done?: string) => Promise<boolean>;
type Move = (item: PlanItem, day: number | null) => void;
type Preview = PlanPreview & { fromAi: boolean };

/**
 * "Kế hoạch 30 ngày" and "Backlog" of one topic group, as two tabs sharing one plan: 3-5 video ideas a day, imported,
 * written by AI or typed in, and the ideas kept for later. An idea is dragged between days and the Backlog.
 */
export function usePlanTabs(topicId: number): {
  tabs: { key: string; label: ReactNode; children: ReactNode }[];
  /** The dialogs both tabs open, rendered once beside the tabs. */
  dialogs: ReactNode;
} {
  const { message } = App.useApp();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [adding, setAdding] = useState<{ day: number | null } | null>(null);
  const [overTab, setOverTab] = useState(false);

  const reload = useCallback(
    async (quiet = false) => {
      try {
        setPlan(await api<Plan>(`/plans/${topicId}`));
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
  const change: Change = async (call, done) => {
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
  };

  const move: Move = (item, day) => {
    if (item.day === day) {
      return;
    }
    void change(() => api<Plan>(`/plans/items/${item.id}`, "PATCH", { day })).then((moved) => {
      // The post on Facebook keeps its time: moving the idea does not move it.
      if (moved && item.status === "scheduled") {
        message.warning("Bài của ý tưởng này đã hẹn giờ; giờ đăng không đổi theo, sửa ở trang video nếu cần.");
      }
    });
  };

  const backlog = plan?.items.filter((item) => item.day === null) ?? [];
  const path = `/plans/${topicId}`;

  function body(content: (plan: Plan) => ReactNode) {
    return plan ? (
      content(plan)
    ) : (
      <Flex justify="center" style={{ padding: 24 }}>
        <Spin />
      </Flex>
    );
  }

  const shared = (
    <>
      <AddIdeaModal
        target={adding}
        onClose={() => setAdding(null)}
        onAdd={async (idea) => {
          if (await change(() => api<Plan>(`${path}/items`, "POST", idea))) {
            setAdding(null);
          }
        }}
      />
      {preview && plan && (
        <PreviewModal
          preview={preview}
          current={plan.items.filter((item) => item.day !== null).length}
          onSave={async () => {
            if (await change(() => api<Plan>(`${path}/items`, "PUT", { ideas: preview.ideas }), "Đã lưu kế hoạch")) {
              setPreview(null);
            }
          }}
          onBacklog={async () => {
            try {
              const result = await api<Plan & { added: number; skipped: number }>(`${path}/backlog`, "POST", {
                ideas: preview.ideas,
              });
              setPlan(result);
              message.success(
                result.skipped
                  ? `Đã thêm ${result.added} ý tưởng vào Backlog, bỏ qua ${result.skipped} chủ đề đã có`
                  : `Đã thêm ${result.added} ý tưởng vào Backlog`,
              );
              setPreview(null);
            } catch (err) {
              message.error(errorMessage(err));
            }
          }}
          onClose={() => setPreview(null)}
        />
      )}
    </>
  );

  const tabs = [
    {
      key: "plan",
      label: "Kế hoạch 30 ngày",
      children: body((plan) => (
        <>
          <PlanView
            plan={plan}
            backlog={backlog}
            working={working}
            change={change}
            move={move}
            onAdd={(day) => setAdding({ day })}
            onPreview={setPreview}
          />
        </>
      )),
    },
    {
      key: "backlog",
      // Dropping an idea of a day on this tab's name sends it to the Backlog.
      label: (
        <span
          data-testid="backlog-tab"
          onDragOver={(event) => {
            event.preventDefault();
            setOverTab(true);
          }}
          onDragLeave={() => setOverTab(false)}
          onDrop={(event) => {
            event.preventDefault();
            setOverTab(false);
            const item = plan?.items.find((row) => row.id === Number(event.dataTransfer.getData(DRAG_TYPE)));
            if (item) {
              move(item, null);
            }
          }}
          style={{ outline: overTab ? "2px dashed #fa8c16" : undefined, padding: "2px 4px", borderRadius: 4 }}
        >
          Backlog{" "}
          <Badge count={backlog.length} showZero color="#bfbfbf" size="small" style={{ marginInlineStart: 4 }} />
        </span>
      ),
      children: body((plan) => (
        <>
          <BacklogView
            plan={plan}
            backlog={backlog}
            change={change}
            move={move}
            onAdd={() => setAdding({ day: null })}
            onPreview={setPreview}
          />
        </>
      )),
    },
  ];
  return { tabs, dialogs: shared };
}

function useImport(topicId: number, onPreview: (preview: Preview) => void) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  async function importFile(file: File) {
    setBusy(true);
    try {
      onPreview({ ...(await upload<PlanPreview>(`/plans/${topicId}/import`, file)), fromAi: false });
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return { busy, importFile };
}

function ImportButton({ topicId, onPreview }: { topicId: number; onPreview: (preview: Preview) => void }) {
  const { busy, importFile } = useImport(topicId, onPreview);
  return (
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
  );
}

function PlanView({
  plan,
  backlog,
  working,
  change,
  move,
  onAdd,
  onPreview,
}: {
  plan: Plan;
  backlog: PlanItem[];
  working: boolean;
  change: Change;
  move: Move;
  onAdd: (day: number) => void;
  onPreview: (preview: Preview) => void;
}) {
  const [showBacklog, setShowBacklog] = useState(false);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [compact, setCompact] = useCompact();
  const path = `/plans/${plan.topic_id}`;
  const byDay = (day: number) => plan.items.filter((item) => item.day === day);
  const planned = plan.items.filter((item) => item.day !== null);
  const shown = planned.filter((item) => matches(item, filters));
  const days = Array.from({ length: PLAN_DAYS }, (_, index) => index + 1);

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
          <PostTimes plan={plan} change={change} />
          <TodayLine plan={plan} />
          <Flex vertical style={{ minWidth: 200, marginLeft: "auto" }}>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Đã làm {plan.made}/{planned.length} ý tưởng
            </Typography.Text>
            <Progress
              percent={planned.length ? Math.round((plan.made / planned.length) * 100) : 0}
              size="small"
              showInfo={false}
            />
          </Flex>
        </Flex>
        <ProgressStrip plan={plan} />
        <VerdictTarget plan={plan} change={change} />
        <Flex wrap gap={8} style={{ marginTop: 12 }}>
          <ImportButton topicId={plan.topic_id} onPreview={onPreview} />
          <Button
            icon={<RobotOutlined />}
            loading={working}
            onClick={() => change(() => api<Plan>(`${path}/generate`, "POST"))}
          >
            {working ? "AI đang lập kế hoạch…" : "Tạo bằng AI"}
          </Button>
        </Flex>
        <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 13 }}>
          File và kế hoạch AI đều hiện bảng xem trước; 30 ngày đang có chỉ bị thay khi bấm “Lưu kế hoạch”, Backlog vẫn
          giữ. AI lập 30 ngày trong 3 lượt (mỗi lượt 10 ngày) với prompt kế hoạch bên dưới và mô hình đang chọn trong
          Cài đặt. Ý tưởng thứ mấy trong ngày thì gợi ý đăng vào giờ đăng thứ đó.
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
                <Button size="small" type="primary" onClick={() => onPreview({ ...plan.draft!, fromAi: true })}>
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

      <Flex wrap gap={8} align="center" data-testid="plan-filters">
        <Select<PlanItemStatus>
          allowClear
          placeholder="Tất cả trạng thái"
          aria-label="Lọc trạng thái"
          value={filters.status}
          onChange={(status) => setFilters({ ...filters, status: status ?? null })}
          options={(Object.keys(STATUS_LABELS) as PlanItemStatus[]).map((status) => ({
            value: status,
            label: STATUS_LABELS[status],
          }))}
          style={{ minWidth: 170 }}
        />
        <Select<string>
          allowClear
          placeholder="Tất cả nhóm nỗi đau"
          aria-label="Lọc nhóm nỗi đau"
          value={filters.group}
          onChange={(group) => setFilters({ ...filters, group: group ?? null })}
          options={[...new Set(planned.map((item) => item.pain_group).filter(Boolean))]
            .sort((a, b) => a.localeCompare(b, "vi"))
            .map((group) => ({ value: group, label: group }))}
          style={{ minWidth: 200 }}
        />
        <Input
          allowClear
          placeholder="Tìm trong tiêu đề, nhóm nỗi đau, nỗi đau, hook"
          aria-label="Tìm ý tưởng"
          value={filters.query}
          onChange={(event) => setFilters({ ...filters, query: event.target.value })}
          style={{ width: 340, maxWidth: "100%" }}
        />
        <Typography.Text type="secondary" data-testid="plan-matches">
          {shown.length}/{planned.length} ý tưởng khớp
        </Typography.Text>
        <Button onClick={() => setFilters(NO_FILTERS)} disabled={!filters.status && !filters.group && !filters.query}>
          Xóa lọc
        </Button>
        <Segmented
          aria-label="Chế độ thẻ"
          value={compact ? "compact" : "full"}
          onChange={(value) => setCompact(value === "compact")}
          options={[
            { value: "full", label: "Đầy đủ" },
            { value: "compact", label: "Gọn" },
          ]}
        />
        <Button
          icon={<InboxOutlined />}
          onClick={() => setShowBacklog((shown) => !shown)}
          style={{ marginLeft: "auto" }}
        >
          {showBacklog ? "Đóng Backlog" : `Mở Backlog (${backlog.length})`}
        </Button>
      </Flex>

      <Row gutter={[12, 12]} wrap={false}>
        <Col flex="auto" style={{ minWidth: 0 }}>
          <Row gutter={[12, 12]}>
            {days.map((day) => (
              <Col key={day} xs={24} md={12} xl={showBacklog ? 12 : 8} xxl={8}>
                <DayCard
                  day={day}
                  plan={plan}
                  items={byDay(day).filter((item) => matches(item, filters))}
                  total={byDay(day).length}
                  compact={compact}
                  onAdd={() => onAdd(day)}
                  onDrop={(id) => {
                    const item = plan.items.find((row) => row.id === id);
                    if (item) move(item, day);
                  }}
                  onChange={change}
                  move={move}
                />
              </Col>
            ))}
          </Row>
        </Col>
        {showBacklog && (
          <Col flex="300px">
            <BacklogPanel plan={plan} backlog={backlog} change={change} move={move} compact={compact} />
          </Col>
        )}
      </Row>
    </Flex>
  );
}

function dayFinished(items: PlanItem[]): boolean {
  return items.length > 0 && items.every((item) => FINISHED.includes(item.status));
}

/** One small cell per day, coloured by how far its ideas are: at a glance, how many days ahead are ready. */
function ProgressStrip({ plan }: { plan: Plan }) {
  const { token } = theme.useToken();
  const legend = [
    { color: token.colorFillSecondary, label: "Trống" },
    { color: token.colorBorder, label: "Có ý tưởng" },
    { color: token.colorWarning, label: "Đang làm" },
    { color: token.colorSuccess, label: "Đủ video" },
    { color: "#722ed1", label: "Đã lên lịch đủ" },
  ];
  function color(day: number): [string, string] {
    const items = plan.items.filter((item) => item.day === day);
    if (items.length === 0) return [legend[0].color, legend[0].label];
    if (dayFinished(items)) return [legend[4].color, legend[4].label];
    if (items.every((item) => item.status !== "idea")) return [legend[3].color, legend[3].label];
    if (items.some((item) => item.status !== "idea")) return [legend[2].color, legend[2].label];
    return [legend[1].color, legend[1].label];
  }
  return (
    <Flex vertical gap={4} style={{ marginTop: 12 }}>
      <Flex gap={3} wrap data-testid="plan-strip">
        {Array.from({ length: PLAN_DAYS }, (_, index) => index + 1).map((day) => {
          const [fill, label] = color(day);
          return (
            <Tooltip key={day} title={`Ngày ${day}: ${label}`}>
              <a
                href={`#plan-day-${day}`}
                aria-label={`Ngày ${day}: ${label}`}
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: 3,
                  background: fill,
                  outline: plan.today_day === day ? `2px solid ${token.colorPrimary}` : undefined,
                  outlineOffset: 1,
                }}
              />
            </Tooltip>
          );
        })}
      </Flex>
      <Flex gap={12} wrap>
        {legend.map((entry) => (
          <Flex key={entry.label} align="center" gap={4}>
            <span
              style={{ width: 10, height: 10, borderRadius: 2, background: entry.color, display: "inline-block" }}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {entry.label}
            </Typography.Text>
          </Flex>
        ))}
      </Flex>
    </Flex>
  );
}

/** The group's posting times: the n-th idea of a day is suggested to go out at the n-th one. */
function PostTimes({ plan, change }: { plan: Plan; change: Change }) {
  return (
    <Flex align="center" gap={8}>
      <Typography.Text>Giờ đăng</Typography.Text>
      <Select
        mode="tags"
        aria-label="Giờ đăng"
        value={plan.post_times}
        tokenSeparators={[",", " "]}
        open={false}
        suffixIcon={null}
        style={{ minWidth: 220 }}
        onChange={(times: string[]) =>
          times.length > 0 && change(() => api<Plan>(`/plans/${plan.topic_id}`, "PATCH", { post_times: times }))
        }
      />
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

/** Where an idea dragged from elsewhere can be dropped. */
function useDropZone(onDrop: (itemId: number) => void) {
  const [over, setOver] = useState(false);
  return {
    over,
    handlers: {
      onDragOver: (event: React.DragEvent) => {
        event.preventDefault();
        setOver(true);
      },
      onDragLeave: () => setOver(false),
      onDrop: (event: React.DragEvent) => {
        event.preventDefault();
        setOver(false);
        const id = Number(event.dataTransfer.getData(DRAG_TYPE));
        if (id) {
          onDrop(id);
        }
      },
    },
  };
}

function DayCard({
  day,
  plan,
  items,
  total,
  compact,
  onAdd,
  onDrop,
  onChange,
  move,
}: {
  day: number;
  plan: Plan;
  /** The day's ideas the filters let through; `total` counts them all. */
  items: PlanItem[];
  total: number;
  compact: boolean;
  onAdd: () => void;
  onDrop: (itemId: number) => void;
  onChange: Change;
  move: Move;
}) {
  // Dropping an idea dragged from another day or the Backlog moves it here, at the end.
  const { over, handlers } = useDropZone((id) => !items.some((item) => item.id === id) && onDrop(id));
  const date = plan.start_date
    ? dayjs(plan.start_date)
        .add(day - 1, "day")
        .locale("vi")
    : null;
  const today = plan.today_day === day;
  return (
    <Card
      size="small"
      id={`plan-day-${day}`}
      data-testid={`plan-day-${day}`}
      title={
        <Flex align="center" gap={8}>
          <span>Ngày {day}</span>
          {date && (
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              {date.format("dddd, DD/MM")}
            </Typography.Text>
          )}
          {today && (
            <Typography.Text style={{ fontSize: 12, fontWeight: 500, color: COLORS.primary }}>Hôm nay</Typography.Text>
          )}
        </Flex>
      }
      extra={
        <Button
          size="small"
          type="text"
          icon={<PlusOutlined />}
          aria-label={`Thêm ý tưởng ngày ${day}`}
          disabled={total >= MAX_PER_DAY}
          onClick={onAdd}
        />
      }
      style={{ height: "100%", outline: over ? "2px dashed #fa8c16" : undefined, scrollMarginTop: 80 }}
      {...handlers}
    >
      <Flex vertical gap={8}>
        {/* Counted on the ideas shown, so the count and the filters agree. */}
        {items.length > 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="plan-day-counts">
            {statusCounts(items)}
          </Typography.Text>
        )}
        {total === 0 && <Typography.Text type="secondary">Chưa có ý tưởng</Typography.Text>}
        {total > 0 && items.length === 0 && <Typography.Text type="secondary">Không có ý tưởng khớp</Typography.Text>}
        {total > 0 && total < MIN_PER_DAY && (
          <Typography.Text type="warning" style={{ fontSize: 12 }}>
            Mới có {total} ý tưởng, nên có {MIN_PER_DAY}–{MAX_PER_DAY}
          </Typography.Text>
        )}
        {items.map((item) => (
          <IdeaCard
            key={item.id}
            item={item}
            onChange={onChange}
            move={move}
            compact={compact}
            shareGoal={plan.share_goal}
          />
        ))}
      </Flex>
    </Card>
  );
}

/** "2 ý tưởng, 1 xong": only the statuses the day has. */
function statusCounts(items: PlanItem[]): string {
  return (Object.keys(STATUS_LABELS) as PlanItemStatus[])
    .map((status) => [status, items.filter((item) => item.status === status).length] as const)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${count} ${STATUS_LABELS[status].toLowerCase()}`)
    .join(", ");
}

/** "Tiến độ verdict": a count of the group's videos against its target, never a verdict. */
function VerdictTarget({ plan, change }: { plan: Plan; change: Change }) {
  const path = `/plans/${plan.topic_id}`;
  const save = (target: number | null) => change(() => api<Plan>(path, "PATCH", { video_target: target }));
  const input = (
    <InputNumber
      size="small"
      aria-label="Số video mục tiêu"
      min={1}
      precision={0}
      placeholder="Số video"
      value={plan.video_target}
      onChange={(value) => typeof value === "number" && value >= 1 && save(value)}
      style={{ width: 96 }}
    />
  );
  if (plan.video_target === null) {
    return (
      <Flex align="center" gap={8} style={{ marginTop: 12 }}>
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          Mục tiêu video cho verdict
        </Typography.Text>
        {input}
      </Flex>
    );
  }
  return (
    <Alert
      type="info"
      style={{ marginTop: 12 }}
      data-testid="plan-verdict"
      title={`Tiến độ verdict: đã làm ${plan.video_count}/${plan.video_target} video`}
      description="Banner chỉ đếm số lượng. Kết luận verdict vẫn họp tay sau khi đủ video đã đăng và đo 48h."
      action={
        <Flex align="center" gap={8}>
          {input}
          <Button size="small" onClick={() => save(null)}>
            Xóa mục tiêu
          </Button>
        </Flex>
      }
    />
  );
}

/** One line per Facebook post of the idea's video: its 48-hour numbers against the goal and its Page's median. */
function PostNumbers({ posts, shareGoal }: { posts: PlanPost[]; shareGoal: number }) {
  if (posts.length === 0) {
    return null;
  }
  const goal = `${(shareGoal * 100).toLocaleString("vi-VN", { maximumFractionDigits: 2 })}%`;
  return (
    <Flex vertical gap={2} style={{ marginTop: 6 }} data-testid="plan-idea-numbers">
      {posts.map((post) => (
        <Typography.Text key={post.publication_id} type="secondary" style={{ fontSize: 12 }}>
          {post.views === null ? (
            `${post.fanpage_name}: chưa đo 48h`
          ) : (
            <>
              {post.fanpage_name}: {post.views.toLocaleString("vi-VN")} view,{" "}
              {(post.shares ?? 0).toLocaleString("vi-VN")} share
              {post.share_rate !== null &&
                `, share/view ${(post.share_rate * 100).toLocaleString("vi-VN", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}% ${post.share_rate >= shareGoal ? "đạt" : "không đạt"} ${goal}`}{" "}
              ,{" "}
              {post.times_median === null ? (
                "chưa đủ dữ liệu (cần ≥5 bài đã đo 48h)"
              ) : (
                <Typography.Text strong={post.times_median >= 10} type="secondary" style={{ fontSize: 12 }}>
                  {post.times_median.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}× trung vị
                </Typography.Text>
              )}
            </>
          )}
        </Typography.Text>
      ))}
    </Flex>
  );
}

/** "Xếp vào ngày…": the days of the plan, a full one cannot be picked. */
function DayPicker({ plan, item, move }: { plan: Plan; item: PlanItem; move: Move }) {
  const count = (day: number) => plan.items.filter((row) => row.day === day).length;
  return (
    <Select<number>
      size="small"
      placeholder="Xếp vào ngày…"
      aria-label="Xếp vào ngày"
      value={null as unknown as number}
      style={{ width: 150 }}
      popupMatchSelectWidth={220}
      onChange={(day) => move(item, day)}
      options={Array.from({ length: PLAN_DAYS }, (_, index) => index + 1).map((day) => {
        const date = plan.start_date ? dayjs(plan.start_date).add(day - 1, "day") : null;
        return {
          value: day,
          disabled: count(day) >= MAX_PER_DAY,
          label: `Ngày ${day}${date ? `, ${date.format("DD/MM")}` : ""} (${count(day)}/${MAX_PER_DAY})`,
        };
      })}
    />
  );
}

function IdeaCard({
  item,
  onChange,
  move,
  dayPicker,
  compact = false,
  shareGoal = 0.002,
}: {
  item: PlanItem;
  onChange: Change;
  move: Move;
  dayPicker?: ReactNode;
  /** "Gọn": the title, status, numbers and buttons only, until this card is opened. */
  compact?: boolean;
  shareGoal?: number;
}) {
  const router = useRouter();
  const { token } = theme.useToken();
  const [open, setOpen] = useState(false);
  const full = !compact || open;
  const path = `/plans/items/${item.id}`;
  // Each field saves on its own when the edit ends (Enter or leaving the field).
  const edit = (field: keyof Omit<PlanIdeaFields, "day">, label: string) => ({
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
      onDragStart={(event) => event.dataTransfer.setData(DRAG_TYPE, String(item.id))}
      data-testid="plan-idea"
      data-status={item.status}
      style={
        {
          border: "1px solid #f0f0f0",
          borderLeft: `3px solid ${statusColor(item.status, token)}`,
          borderRadius: 8,
          padding: 8,
          cursor: "grab",
          background: "#fff",
        } satisfies CSSProperties
      }
    >
      <Flex justify="space-between" align="flex-start" gap={4}>
        <Typography.Paragraph
          strong
          editable={edit("topic", "chủ đề")}
          style={{ margin: 0, flex: 1, cursor: compact ? "pointer" : undefined }}
          onClick={compact ? () => setOpen((value) => !value) : undefined}
        >
          {item.topic}
        </Typography.Paragraph>
        {compact && (
          <Button
            size="small"
            type="text"
            icon={open ? <UpOutlined /> : <DownOutlined />}
            aria-label={open ? "Thu gọn ý tưởng" : "Mở rộng ý tưởng"}
            onClick={() => setOpen((value) => !value)}
          />
        )}
      </Flex>
      {/* On its own line, so the title keeps the card's width. */}
      <Flex align="center" gap={6} wrap style={{ marginTop: 4 }}>
        <Tag color={PLAN_STATUS_COLORS[item.status]} style={{ marginInlineEnd: 0 }}>
          {item.status_label}
        </Tag>
        {item.post_at && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {item.status === "posted" ? "đăng" : "hẹn"} {formatDateTime(item.post_at)}
          </Typography.Text>
        )}
      </Flex>
      <Flex vertical gap={2} style={{ marginTop: 4, fontSize: 13, display: full ? undefined : "none" }}>
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
        {item.suggested_post_at && !item.post_at && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="plan-idea-suggested">
            Dự kiến đăng {formatDateTime(item.suggested_post_at)}
          </Typography.Text>
        )}
      </Flex>
      {dayPicker && <div style={{ marginTop: 6 }}>{dayPicker}</div>}
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
        <Flex gap={2}>
          {item.day !== null && (
            <Tooltip title="Chuyển về Backlog">
              <Button
                size="small"
                type="text"
                icon={<InboxOutlined />}
                aria-label="Chuyển về Backlog"
                onClick={() => move(item, null)}
              />
            </Tooltip>
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
      </Flex>
      <PostNumbers posts={item.posts ?? []} shareGoal={shareGoal} />
    </div>
  );
}

/** The narrow Backlog beside the 30 days: drag an idea from it onto a day, or from a day onto it. */
function BacklogPanel({
  plan,
  backlog,
  change,
  move,
  compact,
}: {
  plan: Plan;
  backlog: PlanItem[];
  change: Change;
  move: Move;
  compact: boolean;
}) {
  const { over, handlers } = useDropZone((id) => {
    const item = plan.items.find((row) => row.id === id);
    if (item) move(item, null);
  });
  return (
    <Card
      size="small"
      title={`Backlog (${backlog.length})`}
      data-testid="backlog-panel"
      style={{ position: "sticky", top: 16, outline: over ? "2px dashed #fa8c16" : undefined }}
      styles={{ body: { maxHeight: "calc(100vh - 140px)", overflowY: "auto" } }}
      {...handlers}
    >
      <Flex vertical gap={8}>
        {backlog.length === 0 && (
          <Typography.Text type="secondary">Kéo ý tưởng của một ngày vào đây để để dành</Typography.Text>
        )}
        {backlog.map((item) => (
          <IdeaCard key={item.id} item={item} onChange={change} move={move} compact={compact} />
        ))}
      </Flex>
    </Card>
  );
}

function BacklogView({
  plan,
  backlog,
  change,
  move,
  onAdd,
  onPreview,
}: {
  plan: Plan;
  backlog: PlanItem[];
  change: Change;
  move: Move;
  onAdd: () => void;
  onPreview: (preview: Preview) => void;
}) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const groups = [...new Set(backlog.map((item) => item.pain_group).filter(Boolean))].sort();
  const shown = backlog.filter((item) => matches(item, { status: null, group, query }));
  return (
    <Flex vertical gap={16} data-testid="backlog-view">
      <Card size="small">
        <Flex wrap gap={8} align="center">
          <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>
            Thêm ý tưởng
          </Button>
          <ImportButton topicId={plan.topic_id} onPreview={onPreview} />
          <Input.Search
            allowClear
            placeholder="Tìm trong Backlog"
            aria-label="Tìm trong Backlog"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            style={{ maxWidth: 260 }}
          />
          <Select
            allowClear
            placeholder="Nhóm nỗi đau"
            aria-label="Lọc nhóm nỗi đau"
            value={group}
            onChange={(value) => setGroup(value ?? null)}
            options={groups.map((name) => ({ value: name, label: name }))}
            style={{ minWidth: 180 }}
          />
        </Flex>
        <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 13 }}>
          Ý tưởng chưa xếp ngày. Chọn “Xếp vào ngày…” trên thẻ, hoặc mở Backlog ở tab Kế hoạch 30 ngày rồi kéo thẻ vào
          một ngày; kéo thẻ của một ngày thả lên tên tab Backlog để chuyển về đây. File nhập không cần cột ngày.
        </Typography.Paragraph>
      </Card>
      {shown.length === 0 ? (
        <Empty description={backlog.length ? "Không có ý tưởng khớp bộ lọc" : "Backlog đang trống"} />
      ) : (
        <Row gutter={[12, 12]}>
          {shown.map((item) => (
            <Col key={item.id} xs={24} md={12} xl={8}>
              <IdeaCard
                item={item}
                onChange={change}
                move={move}
                dayPicker={<DayPicker plan={plan} item={item} move={move} />}
              />
            </Col>
          ))}
        </Row>
      )}
    </Flex>
  );
}

function AddIdeaModal({
  target,
  onClose,
  onAdd,
}: {
  target: { day: number | null } | null;
  onClose: () => void;
  onAdd: (idea: PlanIdeaFields) => Promise<void>;
}) {
  const [form] = Form.useForm<PlanIdeaFields>();
  const [busy, setBusy] = useState(false);
  const day = target?.day ?? null;
  return (
    <FormDrawer
      title={day === null ? "Thêm ý tưởng vào Backlog" : `Thêm ý tưởng ngày ${day}`}
      open={target !== null}
      onClose={onClose}
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
          await onAdd({ ...values, day });
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
    </FormDrawer>
  );
}

function PreviewModal({
  preview,
  current,
  onSave,
  onBacklog,
  onClose,
}: {
  preview: Preview;
  current: number;
  onSave: () => Promise<void>;
  onBacklog: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState<"plan" | "backlog" | null>(null);
  const blocked = preview.errors.length > 0 || preview.ideas.length === 0;
  const run = async (which: "plan" | "backlog", action: () => Promise<void>) => {
    setBusy(which);
    await action();
    setBusy(null);
  };
  return (
    <Modal
      open
      width={1000}
      title={preview.fromAi ? "Xem trước kế hoạch AI lập" : "Xem trước file nhập"}
      onCancel={onClose}
      footer={
        <Flex justify="end" gap={8} wrap>
          <Button onClick={onClose}>{preview.fromAi ? "Để sau" : "Huỷ"}</Button>
          {!preview.fromAi && (
            <Button
              disabled={!preview.can_backlog}
              loading={busy === "backlog"}
              icon={<InboxOutlined />}
              onClick={() => run("backlog", onBacklog)}
            >
              Thêm vào Backlog
            </Button>
          )}
          <Button type="primary" disabled={blocked} loading={busy === "plan"} onClick={() => run("plan", onSave)}>
            Lưu kế hoạch
          </Button>
        </Flex>
      }
    >
      <Flex vertical gap={12}>
        {preview.errors.length > 0 && (
          <Alert
            type="error"
            showIcon
            title={`${preview.errors.length} lỗi, chưa lưu được thành kế hoạch`}
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
            `“Lưu kế hoạch” thay ${current} ý tưởng của 30 ngày (Backlog vẫn giữ); ý tưởng đã có video giữ liên kết nếu cùng chủ đề.`}{" "}
          {!preview.fromAi && "“Thêm vào Backlog” thêm mọi ý tưởng vào Backlog, bỏ qua ngày và chủ đề đã có."}
        </Typography.Text>
        <Table<PlanIdeaFields>
          size="small"
          rowKey={(row) => `${row.day}-${row.topic}`}
          dataSource={preview.ideas}
          pagination={{ pageSize: 40, hideOnSinglePage: true }}
          scroll={{ x: 900, y: 420 }}
          columns={[
            { title: "Ngày", dataIndex: "day", width: 64, render: (day: number | null) => day ?? "—" },
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
