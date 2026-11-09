"use client";

import { useMe } from "@/components/MeContext";
import {
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  ImportOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  SettingOutlined,
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
  Drawer,
  Empty,
  Flex,
  Form,
  Grid,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
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
import AutoRuns from "@/components/plan/AutoRuns";
import { COLORS } from "@/app/theme";

const PLAN_DAYS = 30;
// Pages post 1-2 videos a day, some more: plans.MIN_PER_DAY and MAX_PER_DAY of the api.
const MIN_PER_DAY = 1;
const MAX_PER_DAY = 10;
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

type Change = (call: () => Promise<Plan>, done?: string) => Promise<boolean>;
type Move = (item: PlanItem, day: number | null) => void;
type Preview = PlanPreview & { fromAi: boolean };

/**
 * "Kế hoạch 30 ngày" and "Backlog" of one topic group, as two tabs sharing one plan: 1-10 video ideas a day, imported,
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
  const [showSettings, setShowSettings] = useState(false);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [compact, setCompact] = useCompact();
  // The day shown under the calendar: today while the plan runs, else day 1; a new start date moves it to today.
  const runningDay = (today: number | null) => (today !== null && today >= 1 && today <= PLAN_DAYS ? today : 1);
  const [selected, setSelected] = useState(() => runningDay(plan.today_day));
  // The day open in the drawer (over a mask); closing it keeps the filters, the chosen day and the scroll.
  const [openDay, setOpenDay] = useState<number | null>(null);
  const openOn = (day: number) => {
    setSelected(day);
    setOpenDay(day);
  };
  const closeDay = useCallback(() => setOpenDay(null), []);
  const [todaySeen, setTodaySeen] = useState(plan.today_day);
  if (todaySeen !== plan.today_day) {
    setTodaySeen(plan.today_day);
    setSelected(runningDay(plan.today_day));
  }
  const path = `/plans/${plan.topic_id}`;
  const byDay = (day: number) => plan.items.filter((item) => item.day === day);
  const planned = plan.items.filter((item) => item.day !== null);
  const shown = planned.filter((item) => matches(item, filters));
  const scheduled = planned.filter((item) => item.status === "scheduled").length;
  const empty = Array.from({ length: PLAN_DAYS }, (_, index) => index + 1).filter((day) => !byDay(day).length).length;

  return (
    <Flex vertical gap={16} data-testid="plan-tab">
      <Card size="small">
        <TodayStrip plan={plan} change={change} />
        <Typography.Text type="secondary" style={{ display: "block", marginTop: 12 }} data-testid="plan-summary">
          Đã làm {plan.made}/{planned.length} · Đã lên lịch {scheduled} · Ngày còn trống {empty}
        </Typography.Text>
        <VerdictTarget plan={plan} change={change} />
        <Flex wrap gap={8} style={{ marginTop: 12 }}>
          <Button
            icon={<SettingOutlined />}
            aria-expanded={showSettings}
            onClick={() => setShowSettings((value) => !value)}
          >
            Thiết lập
          </Button>
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
          File và kế hoạch AI hiện bảng xem trước; 30 ngày chỉ bị thay khi bấm “Lưu kế hoạch”, Backlog vẫn giữ.
        </Typography.Paragraph>
        {showSettings && <PlanSettings plan={plan} change={change} onClose={() => setShowSettings(false)} />}
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

      <Row gutter={[12, 12]} wrap={false}>
        <Col flex="auto" style={{ minWidth: 0 }}>
          <Flex vertical gap={12}>
            <StatusLegend />
            <MonthCalendar
              plan={plan}
              selected={selected}
              onSelect={openOn}
              onAdd={(day) => {
                openOn(day);
                onAdd(day);
              }}
              move={move}
            />
            <Flex justify="flex-end">
              <Button icon={<InboxOutlined />} onClick={() => setShowBacklog((open) => !open)}>
                {showBacklog ? "Đóng Backlog" : `Mở Backlog (${backlog.length})`}
              </Button>
            </Flex>
          </Flex>

          <Drawer
            open={openDay !== null}
            onClose={closeDay}
            // A press on the mask closes it, like the × (owner's choice, 2026-11-09); the filters, the chosen day and
            // the page's scroll stay. While it is open the Backlog cannot be dragged from.
            mask
            maskClosable
            size="min(520px, 100vw)"
            data-testid="plan-day-drawer"
            title={dayTitle(plan, selected)}
            extra={
              <Button
                size="small"
                icon={<PlusOutlined />}
                aria-label={`Thêm ý tưởng ngày ${selected}`}
                disabled={byDay(selected).length >= MAX_PER_DAY}
                onClick={() => onAdd(selected)}
              >
                Thêm ý
              </Button>
            }
          >
            <Flex vertical gap={12}>
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
                <Button
                  onClick={() => setFilters(NO_FILTERS)}
                  disabled={!filters.status && !filters.group && !filters.query}
                >
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
              </Flex>
              {/* The chosen day in full; the filters and "Gọn" apply here, never to the calendar. */}
              <DayCard
                bare
                day={selected}
                plan={plan}
                items={byDay(selected).filter((item) => matches(item, filters))}
                total={byDay(selected).length}
                compact={compact}
                onAdd={() => onAdd(selected)}
                onDrop={(id) => {
                  const item = plan.items.find((row) => row.id === id);
                  if (item) move(item, selected);
                }}
                onChange={change}
                move={move}
              />
            </Flex>
          </Drawer>
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

/** The date of a plan day, once a start date is set. */
function dayDate(plan: Plan, day: number) {
  return plan.start_date
    ? dayjs(plan.start_date)
        .add(day - 1, "day")
        .locale("vi")
    : null;
}

/** The drawer's title: "Ngày N — Thứ …, dd/mm" once the plan has a start date, with "Hôm nay" on today. */
function dayTitle(plan: Plan, day: number): ReactNode {
  const date = dayDate(plan, day);
  const weekday = date ? date.format("dddd") : "";
  return (
    <Flex align="center" gap={8}>
      <span data-testid="plan-day-title">
        Ngày {day}
        {date && ` — ${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}, ${date.format("DD/MM")}`}
      </span>
      {plan.today_day === day && (
        <Typography.Text style={{ fontSize: 12, fontWeight: 500, color: COLORS.primary }}>Hôm nay</Typography.Text>
      )}
    </Flex>
  );
}

/** The status colours of the idea chips. */
function StatusLegend() {
  const { token } = theme.useToken();
  return (
    <Flex gap={12} wrap data-testid="plan-legend">
      {(Object.keys(STATUS_LABELS) as PlanItemStatus[]).map((status) => (
        <Flex key={status} align="center" gap={4}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              background: statusColor(status, token),
              display: "inline-block",
            }}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {STATUS_LABELS[status]}
          </Typography.Text>
        </Flex>
      ))}
    </Flex>
  );
}

const WEEKS = [0, 1, 2, 3, 4].map((week) =>
  Array.from({ length: Math.min(7, PLAN_DAYS - week * 7) }, (_, index) => week * 7 + index + 1),
);

/** The 30 days as five weeks of day cells, each listing its ideas as chips; a cell picks the day shown below. */
function MonthCalendar({
  plan,
  selected,
  onSelect,
  onAdd,
  move,
}: {
  plan: Plan;
  selected: number;
  onSelect: (day: number) => void;
  onAdd: (day: number) => void;
  move: Move;
}) {
  const screens = Grid.useBreakpoint();
  const columns = screens.md ? 7 : screens.sm ? 3 : 2;
  return (
    <Flex vertical gap={12} data-testid="plan-calendar">
      {WEEKS.map((days, index) => {
        const items = plan.items.filter((item) => item.day !== null && days.includes(item.day));
        const first = dayDate(plan, days[0]);
        const last = dayDate(plan, days[days.length - 1]);
        return (
          <div key={index} data-testid={`plan-week-${index + 1}`}>
            <Flex wrap gap={8} align="baseline" style={{ marginBottom: 6 }}>
              <Typography.Text strong>
                Tuần {index + 1} ·{" "}
                {first && last
                  ? `${first.format("DD/MM")} – ${last.format("DD/MM")}`
                  : `ngày ${days[0]}–${days[days.length - 1]}`}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {items.length} ý tưởng · {items.filter((item) => item.status !== "idea").length} đã làm ·{" "}
                {items.filter((item) => item.status === "scheduled").length} đã lên lịch
              </Typography.Text>
            </Flex>
            <div style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gap: 6 }}>
              {days.map((day) => (
                <DayCell
                  key={day}
                  day={day}
                  plan={plan}
                  selected={day === selected}
                  onSelect={() => onSelect(day)}
                  onAdd={() => onAdd(day)}
                  move={move}
                />
              ))}
            </div>
          </div>
        );
      })}
    </Flex>
  );
}

function DayCell({
  day,
  plan,
  selected,
  onSelect,
  onAdd,
  move,
}: {
  day: number;
  plan: Plan;
  selected: boolean;
  onSelect: () => void;
  onAdd: () => void;
  move: Move;
}) {
  const { token } = theme.useToken();
  const { message } = App.useApp();
  const items = plan.items.filter((item) => item.day === day);
  // Dropping an idea moves it here, as "Xếp vào ngày…" does: a full day takes no more.
  const { over, handlers } = useDropZone((id) => {
    const item = plan.items.find((row) => row.id === id);
    if (!item || item.day === day) return;
    if (items.length >= MAX_PER_DAY) {
      message.warning(`Ngày ${day} đã đủ ${MAX_PER_DAY} ý tưởng`);
      return;
    }
    move(item, day);
  });
  const date = dayDate(plan, day);
  const today = plan.today_day === day;
  return (
    <div
      data-testid={`plan-day-${day}`}
      data-selected={selected}
      onClick={onSelect}
      style={{
        minHeight: 96,
        minWidth: 0,
        padding: 6,
        borderRadius: 8,
        background: token.colorBgContainer,
        border: `${selected ? 2 : 1}px solid ${selected ? token.colorPrimary : token.colorBorderSecondary}`,
        outline: over ? "2px dashed #fa8c16" : undefined,
        cursor: "pointer",
      }}
      {...handlers}
    >
      <Flex justify="space-between" align="center" gap={4}>
        <button
          type="button"
          aria-label={`Chọn ngày ${day}`}
          aria-pressed={selected}
          onClick={(event) => {
            event.stopPropagation();
            onSelect();
          }}
          style={{
            all: "unset",
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 500,
            textTransform: "none",
          }}
        >
          {date ? date.format("dd DD/MM") : `Ngày ${day}`}
        </button>
        {today && (
          <Typography.Text style={{ fontSize: 11, fontWeight: 500, color: COLORS.primary }}>Hôm nay</Typography.Text>
        )}
      </Flex>
      <Flex vertical gap={3} style={{ marginTop: 4 }}>
        {items.map((item) => (
          <Tooltip key={item.id} title={`${item.topic} · ${item.status_label}`}>
            <div
              draggable
              onDragStart={(event) => event.dataTransfer.setData(DRAG_TYPE, String(item.id))}
              data-testid="plan-chip"
              data-status={item.status}
              style={{
                fontSize: 12,
                lineHeight: "18px",
                padding: "0 4px",
                borderRadius: 4,
                borderLeft: `3px solid ${statusColor(item.status, token)}`,
                background: token.colorFillQuaternary,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                cursor: "grab",
              }}
            >
              {item.topic}
            </div>
          </Tooltip>
        ))}
        {items.length === 0 && (
          <Button
            size="small"
            type="dashed"
            block
            aria-label={`Thêm ý ngày ${day}`}
            onClick={(event) => {
              event.stopPropagation();
              onAdd();
            }}
          >
            + Thêm ý
          </Button>
        )}
      </Flex>
    </div>
  );
}

/** "Thiết lập": changed in place and sent together by "Lưu", only the fields that changed; "Huỷ" drops them. */
function PlanSettings({ plan, change, onClose }: { plan: Plan; change: Change; onClose: () => void }) {
  const [start, setStart] = useState(plan.start_date);
  const [perDay, setPerDay] = useState<number | null>(plan.per_day);
  const [times, setTimes] = useState(plan.post_times);
  const [target, setTarget] = useState<number | null>(plan.video_target);
  const [busy, setBusy] = useState(false);

  async function save() {
    const changes: Record<string, unknown> = {};
    if (start !== plan.start_date) changes.start_date = start;
    if (perDay !== null && perDay !== plan.per_day) changes.per_day = perDay;
    if (times.join() !== plan.post_times.join()) changes.post_times = times;
    if (target !== plan.video_target) changes.video_target = target;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setBusy(true);
    const saved = await change(() => api<Plan>(`/plans/${plan.topic_id}`, "PATCH", changes), "Đã lưu thiết lập");
    setBusy(false);
    if (saved) onClose();
  }

  return (
    <Card size="small" style={{ marginTop: 12 }} data-testid="plan-settings">
      <Flex wrap gap={16} align="center">
        <Flex align="center" gap={8}>
          <Typography.Text>Ngày bắt đầu</Typography.Text>
          <DatePicker
            aria-label="Ngày bắt đầu kế hoạch"
            format="DD/MM/YYYY"
            placeholder="Chọn ngày 1"
            value={start ? dayjs(start) : null}
            onChange={(value) => setStart(value ? value.format("YYYY-MM-DD") : null)}
          />
        </Flex>
        <Flex align="center" gap={8}>
          <Typography.Text>Số ý tưởng mỗi ngày</Typography.Text>
          <InputNumber
            aria-label="Số ý tưởng mỗi ngày"
            min={MIN_PER_DAY}
            max={MAX_PER_DAY}
            precision={0}
            value={perDay}
            onChange={(value) => setPerDay(value)}
            style={{ width: 72 }}
          />
        </Flex>
        <PostTimes value={times} onChange={setTimes} />
        <Flex align="center" gap={8}>
          <Typography.Text>Mục tiêu video cho verdict</Typography.Text>
          <InputNumber
            aria-label="Mục tiêu video"
            min={1}
            precision={0}
            placeholder="Không đặt"
            value={target}
            onChange={(value) => setTarget(typeof value === "number" ? value : null)}
            style={{ width: 110 }}
          />
        </Flex>
      </Flex>
      <Flex gap={8} style={{ marginTop: 12 }}>
        <Button type="primary" loading={busy} onClick={() => void save()}>
          Lưu
        </Button>
        <Button disabled={busy} onClick={onClose}>
          Huỷ
        </Button>
      </Flex>
    </Card>
  );
}

/** The group's posting times: the n-th idea of a day is suggested to go out at the n-th one. */
function PostTimes({ value, onChange }: { value: string[]; onChange: (times: string[]) => void }) {
  return (
    <Flex align="center" gap={8}>
      <Typography.Text>Giờ đăng</Typography.Text>
      <Select
        mode="tags"
        aria-label="Giờ đăng"
        value={value}
        tokenSeparators={[",", " "]}
        open={false}
        suffixIcon={null}
        style={{ minWidth: 220 }}
        onChange={(times: string[]) => onChange(times)}
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

/** "Hôm nay": today's ideas with their next step, or why there is no today yet. */
function TodayStrip({ plan, change }: { plan: Plan; change: Change }) {
  const { token } = theme.useToken();
  const running = plan.today_day !== null && plan.today_day >= 1 && plan.today_day <= PLAN_DAYS;
  const today = running ? plan.items.filter((item) => item.day === plan.today_day) : [];
  return (
    <Flex vertical gap={6} data-testid="plan-today-strip">
      <TodayLine plan={plan} />
      {running && today.length === 0 && <Typography.Text type="secondary">Hôm nay chưa có ý tưởng</Typography.Text>}
      {today.map((item) => (
        <Flex
          key={item.id}
          wrap
          align="center"
          gap={8}
          data-testid="plan-today-idea"
          style={{ borderLeft: `3px solid ${statusColor(item.status, token)}`, paddingLeft: 8 }}
        >
          <Typography.Text strong style={{ flex: "1 1 200px", minWidth: 0 }}>
            {item.topic}
          </Typography.Text>
          <Tag color={PLAN_STATUS_COLORS[item.status]} style={{ marginInlineEnd: 0 }}>
            {item.status_label}
          </Tag>
          <IdeaAction item={item} />
          <EditIdeaButton item={item} onChange={change} />
        </Flex>
      ))}
      <AutoRuns topicId={plan.topic_id} />
    </Flex>
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
  bare,
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
  /** In the day's drawer, whose own title names the day and adds an idea. */
  bare?: boolean;
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
  const date = dayDate(plan, day);
  const today = plan.today_day === day;
  return (
    <Card
      size="small"
      data-testid="plan-day-panel"
      variant={bare ? "borderless" : undefined}
      styles={bare ? { body: { padding: 0 } } : undefined}
      title={
        bare ? undefined : (
          <Flex align="center" gap={8}>
            <span>Ngày {day}</span>
            {date && (
              <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                {date.format("dddd, DD/MM")}
              </Typography.Text>
            )}
            {today && (
              <Typography.Text style={{ fontSize: 12, fontWeight: 500, color: COLORS.primary }}>
                Hôm nay
              </Typography.Text>
            )}
          </Flex>
        )
      }
      extra={
        bare ? undefined : (
          <Button
            size="small"
            type="text"
            icon={<PlusOutlined />}
            aria-label={`Thêm ý tưởng ngày ${day}`}
            disabled={total >= MAX_PER_DAY}
            onClick={onAdd}
          />
        )
      }
      style={{ outline: over ? "2px dashed #fa8c16" : undefined }}
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
          {post.latest_views !== null && (
            <span data-testid="plan-idea-latest-views"> · hiện {post.latest_views.toLocaleString("vi-VN")} view</span>
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
  const { token } = theme.useToken();
  const [open, setOpen] = useState(false);
  const full = !compact || open;
  const path = `/plans/items/${item.id}`;
  // Only whoever added the idea deletes it.
  const { me } = useMe();
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
        <Typography.Text type="secondary">{item.pain_group || "—"}</Typography.Text>
        <Typography.Paragraph style={{ margin: 0, fontSize: 13 }}>
          <Typography.Text type="secondary">Nỗi đau: </Typography.Text>
          {item.pain}
        </Typography.Paragraph>
        <Typography.Paragraph style={{ margin: 0, fontSize: 13 }}>
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
        <Flex align="center" gap={6}>
          <IdeaAction item={item} />
          <EditIdeaButton item={item} onChange={onChange} />
        </Flex>
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
          {item.created_by_id === me.id && (
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
          )}
        </Flex>
      </Flex>
      <PostNumbers posts={item.posts ?? []} shareGoal={shareGoal} />
    </div>
  );
}

/** The idea's next step: "Tạo video", or "Mở video" once it has one. */
function IdeaAction({ item }: { item: PlanItem }) {
  const router = useRouter();
  return item.video_id ? (
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
  );
}

function EditIdeaButton({ item, onChange }: { item: PlanItem; onChange: Change }) {
  const [editing, setEditing] = useState(false);
  return (
    <>
      <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(true)}>
        Sửa
      </Button>
      <EditIdeaDrawer item={item} open={editing} onClose={() => setEditing(false)} onChange={onChange} />
    </>
  );
}

/** "Sửa ý tưởng": the four fields of an idea in one form, saved together by "Lưu"; "Huỷ" changes nothing. */
function EditIdeaDrawer({
  item,
  open,
  onClose,
  onChange,
}: {
  item: PlanItem;
  open: boolean;
  onClose: () => void;
  onChange: Change;
}) {
  const [form] = Form.useForm<Omit<PlanIdeaFields, "day">>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Back to the idea as saved, so what "Huỷ" dropped is not there when the form opens again.
  const close = () => {
    setError(null);
    form.resetFields();
    onClose();
  };
  return (
    <FormDrawer
      title="Sửa ý tưởng"
      open={open}
      onClose={close}
      onOk={() => form.submit()}
      okText="Lưu"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 16 }} />}
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{ topic: item.topic, pain_group: item.pain_group, pain: item.pain, hook: item.hook }}
        onFinish={async (values) => {
          setBusy(true);
          setError(null);
          try {
            // One request for the four fields; a refusal stays in the form, which stays open.
            const plan = await api<Plan>(`/plans/items/${item.id}`, "PATCH", values);
            await onChange(async () => plan, "Đã lưu ý tưởng");
            close();
          } catch (err) {
            setError(errorMessage(err));
          } finally {
            setBusy(false);
          }
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
