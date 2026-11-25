"use client";

import { SearchOutlined, SettingOutlined, HolderOutlined } from "@ant-design/icons";
import { Button, Checkbox, Empty, Flex, Input, Popover, Typography } from "antd";
import { useState } from "react";

export type PickableColumn<K extends string> = { key: K; title: string; group: string };

/** The shown columns of a table, in their shown order, remembered in this browser under `storageKey`. A key saved
 * before a column existed or after one was dropped is ignored; with nothing saved (or a browser that refuses
 * storage) `initial` is shown. */
export function useRememberedColumns<K extends string>(
  storageKey: string,
  known: readonly K[],
  initial: readonly K[],
): [K[], (next: K[]) => void] {
  const [keys, setKeys] = useState<K[]>(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey) ?? "null");
      if (Array.isArray(saved)) return saved.filter((key): key is K => known.includes(key));
    } catch {
      // A browser that refuses storage shows the first choice.
    }
    return [...initial];
  });
  function choose(next: K[]) {
    setKeys(next);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }
  return [keys, choose];
}

/** "Cột": search, columns grouped like Meta's, drag to reorder, and "Áp dụng" / "Hủy" (nothing changes until Áp
 * dụng). `shown` is the order the table uses; the columns not shown follow it in the box, in `columns` order. */
export default function ColumnPicker<K extends string>({
  columns,
  shown,
  onApply,
}: {
  columns: PickableColumn<K>[];
  shown: K[];
  onApply: (next: K[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  // The whole order, shown columns first as they are, and which are ticked.
  const [order, setOrder] = useState<K[]>([]);
  const [ticked, setTicked] = useState<K[]>([]);
  const [dragging, setDragging] = useState<K | null>(null);

  function show(next: boolean) {
    setOpen(next);
    if (!next) return;
    setSearch("");
    setTicked(shown);
    setOrder([...shown, ...columns.map((column) => column.key).filter((key) => !shown.includes(key))]);
  }
  function drop(target: K) {
    if (dragging === null || dragging === target) return;
    const next = order.filter((key) => key !== dragging);
    next.splice(next.indexOf(target) + (order.indexOf(dragging) < order.indexOf(target) ? 1 : 0), 0, dragging);
    setOrder(next);
    setDragging(null);
  }

  const byKey = new Map(columns.map((column) => [column.key, column]));
  const needle = search.trim().toLowerCase();
  const groups = [...new Set(columns.map((column) => column.group))]
    .map((group) => ({
      group,
      keys: order.filter(
        (key) => byKey.get(key)?.group === group && byKey.get(key)!.title.toLowerCase().includes(needle),
      ),
    }))
    .filter((row) => row.keys.length > 0);

  const content = (
    <Flex vertical gap={8} style={{ width: 300 }}>
      <Input
        allowClear
        prefix={<SearchOutlined />}
        placeholder="Tìm cột"
        aria-label="Tìm cột"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div style={{ maxHeight: 340, overflowY: "auto" }}>
        {groups.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Không có cột nào khớp" />}
        {groups.map(({ group, keys }) => (
          <Flex key={group} vertical gap={2} style={{ marginBottom: 8 }}>
            <Typography.Text type="secondary" strong style={{ fontSize: 12 }}>
              {group}
            </Typography.Text>
            {keys.map((key) => (
              <Flex
                key={key}
                align="center"
                gap={8}
                draggable
                onDragStart={() => setDragging(key)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => drop(key)}
                onDragEnd={() => setDragging(null)}
                style={{ padding: "2px 4px", opacity: dragging === key ? 0.4 : 1 }}
                data-testid={`column-option-${key}`}
              >
                <HolderOutlined style={{ cursor: "grab", color: "#999" }} aria-hidden />
                <Checkbox
                  checked={ticked.includes(key)}
                  onChange={(event) =>
                    setTicked(event.target.checked ? [...ticked, key] : ticked.filter((one) => one !== key))
                  }
                >
                  {byKey.get(key)!.title}
                </Checkbox>
              </Flex>
            ))}
          </Flex>
        ))}
      </div>
      <Flex justify="flex-end" gap={8}>
        <Button size="small" onClick={() => show(false)}>
          Hủy
        </Button>
        <Button
          size="small"
          type="primary"
          onClick={() => {
            onApply(order.filter((key) => ticked.includes(key)));
            setOpen(false);
          }}
        >
          Áp dụng
        </Button>
      </Flex>
    </Flex>
  );

  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      title="Cột hiện trong bảng"
      open={open}
      onOpenChange={show}
      content={content}
    >
      <Button size="small" icon={<SettingOutlined />}>
        Cột
      </Button>
    </Popover>
  );
}
