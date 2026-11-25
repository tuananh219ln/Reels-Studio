"use client";

import EmptyState from "@/components/EmptyState";
import { fillColumn } from "@/components/fillColumn";
import { rowLink } from "@/lib/rowLink";
import { Table } from "antd";
import type { ColumnsType, TableProps } from "antd/es/table";
import { useRouter } from "next/navigation";
import type { HTMLAttributes, Key, ReactNode } from "react";

/** The one table of every list of videos or posts: the same size, paging, sideways scroll, empty state and row, with
 * the row's actions (a ⋮ menu) in a last column pinned to the right, so the button is always in the same place.
 * A page gives only its own columns, each with a `width`: on a wide screen the spare width goes to an empty column
 * before the actions, so the page's columns stay side by side. `size` is "middle" for a page's own list and "small"
 * for one inside a card. */
export default function VideoTable<T extends object>({
  rows,
  columns,
  rowKey,
  actions,
  actionsWidth = 96,
  size = "middle",
  loading,
  empty = "Chưa có video nào",
  page,
  pageSize = 50,
  total,
  rowHref,
  rowTestId,
  testId,
  tableProps,
}: {
  rows: T[];
  columns: ColumnsType<T>;
  rowKey: keyof T | ((row: T) => Key);
  /** The row's ⋮ menu (VideoActions), in the last column. */
  actions?: (row: T) => ReactNode;
  actionsWidth?: number;
  size?: "middle" | "small";
  loading?: boolean;
  empty?: ReactNode;
  /** The table's page in the address (`useUrlPage`). */
  page?: { current: number; onChange: (page: number) => void };
  pageSize?: number;
  /** All rows when the api pages them; left out when `rows` is the whole list. */
  total?: number;
  /** A click on the row (not on a link or button in it) opens this address; Ctrl/Cmd-click opens a new tab. */
  rowHref?: (row: T) => string;
  rowTestId?: string;
  testId?: string;
  /** Anything else the table takes (sorting, expanding), by exception. */
  tableProps?: Omit<TableProps<T>, "columns" | "dataSource" | "rowKey" | "size" | "loading">;
}) {
  const router = useRouter();
  const all: ColumnsType<T> = actions
    ? [
        ...columns,
        fillColumn<T>(),
        {
          key: "actions",
          fixed: "right",
          width: actionsWidth,
          render: (_: unknown, row: T) => actions(row),
        },
      ]
    : [...columns, fillColumn<T>()];
  return (
    <Table<T>
      data-testid={testId}
      rowKey={rowKey as TableProps<T>["rowKey"]}
      size={size}
      loading={loading}
      dataSource={rows}
      columns={all}
      pagination={{
        pageSize,
        hideOnSinglePage: true,
        showSizeChanger: false,
        ...(total === undefined ? {} : { total }),
        ...page,
      }}
      scroll={{ x: "max-content" }}
      locale={{ emptyText: typeof empty === "string" ? <EmptyState description={empty} /> : empty }}
      onRow={(row) =>
        ({
          ...(rowHref ? { ...rowLink((href) => router.push(href), rowHref(row)), style: { cursor: "pointer" } } : {}),
          ...(rowTestId ? { "data-testid": rowTestId } : {}),
        }) as HTMLAttributes<HTMLElement>
      }
      {...tableProps}
    />
  );
}
