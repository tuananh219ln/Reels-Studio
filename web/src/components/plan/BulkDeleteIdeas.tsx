"use client";

import { DeleteOutlined } from "@ant-design/icons";
import { Alert, Button, Flex, Select, Tree, Typography, type TreeDataNode } from "antd";
import dayjs from "dayjs";
import "dayjs/locale/vi";
import { useState } from "react";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import { api, type Plan, type PlanItem, type PlanItemStatus } from "@/lib/api";

const PLAN_DAYS = 30;
const BACKLOG = "backlog";

type Change = (call: () => Promise<Plan>, done?: string) => Promise<boolean>;

/** "Xóa nhiều ý tưởng" on the 30-day plan: ticks by week, day or idea, then one delete. Only the member's own ideas
 * can be ticked, as one by one (the api refuses the whole choice otherwise); a video made from an idea stays. */
export default function BulkDeleteIdeas({
  plan,
  statusLabels,
  change,
}: {
  plan: Plan;
  statusLabels: Record<PlanItemStatus, string>;
  change: Change;
}) {
  const { me } = useMe();
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState<number[]>([]);
  const [status, setStatus] = useState<PlanItemStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const shown = plan.items.filter((item) => !status || item.status === status);
  const mine = (item: PlanItem) => item.created_by_id === me.id;
  const dateOf = (day: number) =>
    plan.start_date
      ? dayjs(plan.start_date)
          .add(day - 1, "day")
          .locale("vi")
          .format("dd DD/MM")
      : null;
  const leaf = (item: PlanItem): TreeDataNode => ({
    key: item.id,
    title: (
      <span>
        {item.topic}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {" "}
          · {statusLabels[item.status]}
          {item.video_id ? ", có video (video giữ nguyên)" : ""}
          {mine(item) ? "" : ", của thành viên khác"}
        </Typography.Text>
      </span>
    ),
    isLeaf: true,
    disableCheckbox: !mine(item),
  });
  const dayNode = (day: number): TreeDataNode | null => {
    const items = shown.filter((item) => item.day === day);
    if (!items.length) return null;
    const date = dateOf(day);
    return {
      key: `day-${day}`,
      title: `Ngày ${day}${date ? `, ${date}` : ""} (${items.length})`,
      children: items.map(leaf),
      disableCheckbox: !items.some(mine),
    };
  };
  const weeks: TreeDataNode[] = [0, 1, 2, 3, 4].flatMap((week) => {
    const days = Array.from({ length: Math.min(7, PLAN_DAYS - week * 7) }, (_, index) => week * 7 + index + 1)
      .map(dayNode)
      .filter((node): node is TreeDataNode => node !== null);
    if (!days.length) return [];
    const first = week * 7 + 1;
    const last = Math.min(PLAN_DAYS, first + 6);
    return [
      {
        key: `week-${week + 1}`,
        title: `Tuần ${week + 1}, ngày ${first}–${last}`,
        children: days,
        disableCheckbox: days.every((node) => node.disableCheckbox),
      },
    ];
  });
  const backlog = shown.filter((item) => item.day === null);
  const tree: TreeDataNode[] = backlog.length
    ? [
        ...weeks,
        {
          key: BACKLOG,
          title: `Backlog (${backlog.length})`,
          children: backlog.map(leaf),
          disableCheckbox: !backlog.some(mine),
        },
      ]
    : weeks;

  // Only ideas count: the week and day keys are strings.
  const ids = checked.filter((key) => plan.items.some((item) => item.id === key && mine(item)));

  function close() {
    setOpen(false);
    setChecked([]);
    setStatus(null);
  }

  async function remove() {
    setBusy(true);
    const done = await change(
      () => api<Plan>(`/plans/${plan.topic_id}/items/delete`, "POST", { ids }),
      `Đã xóa ${ids.length} ý tưởng`,
    );
    setBusy(false);
    if (done) close();
  }

  return (
    <>
      <Button icon={<DeleteOutlined />} disabled={!plan.items.length} onClick={() => setOpen(true)}>
        Xóa nhiều ý tưởng
      </Button>
      <FormDrawer
        title="Xóa nhiều ý tưởng"
        open={open}
        onClose={close}
        width={620}
        okText={ids.length ? `Xóa ${ids.length} ý tưởng` : "Xóa"}
        okButtonProps={{ danger: true, disabled: !ids.length }}
        confirmLoading={busy}
        onOk={remove}
      >
        <Flex vertical gap={12} data-testid="plan-bulk-delete">
          <Alert
            type="info"
            showIcon
            title="Tích cả tuần, cả ngày hoặc từng ý tưởng. Chỉ xóa được ý tưởng do bạn tạo; video đã làm từ ý tưởng vẫn giữ nguyên."
          />
          <Flex gap={8} wrap align="center">
            <Select<PlanItemStatus>
              allowClear
              placeholder="Mọi trạng thái"
              aria-label="Lọc trạng thái khi xóa"
              value={status}
              onChange={(value) => {
                setStatus(value ?? null);
                setChecked([]);
              }}
              options={(Object.keys(statusLabels) as PlanItemStatus[]).map((value) => ({
                value,
                label: statusLabels[value],
              }))}
              style={{ minWidth: 170 }}
            />
            <Button onClick={() => setChecked(shown.filter(mine).map((item) => item.id))} disabled={!shown.some(mine)}>
              Chọn tất cả của tôi
            </Button>
            <Button onClick={() => setChecked([])} disabled={!checked.length}>
              Bỏ chọn
            </Button>
            <Typography.Text type="secondary" data-testid="plan-bulk-count">
              Đã chọn {ids.length} ý tưởng
            </Typography.Text>
          </Flex>
          {tree.length ? (
            <Tree
              checkable
              selectable={false}
              defaultExpandAll
              treeData={tree}
              checkedKeys={checked}
              onCheck={(keys) => {
                const list = Array.isArray(keys) ? keys : keys.checked;
                setChecked(list.filter((key): key is number => typeof key === "number"));
              }}
            />
          ) : (
            <Typography.Text type="secondary">Không có ý tưởng nào khớp</Typography.Text>
          )}
        </Flex>
      </FormDrawer>
    </>
  );
}
