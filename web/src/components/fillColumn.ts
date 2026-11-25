import type { ColumnType } from "antd/es/table";

/**
 * An empty column that takes the table's spare width, so on a wide screen the columns stay side by side and the
 * space goes to one gap before the row's actions instead of between every column. It works only when every other
 * column has a `width` and its content is capped in pixels (a nowrap or "…" line capped only in % grows its column to
 * the whole line). On a narrow screen it is 0 wide.
 */
export function fillColumn<T>(): ColumnType<T> {
  return {
    key: "__fill",
    className: "table-fill",
    onHeaderCell: () => ({ "aria-hidden": true }) as React.HTMLAttributes<HTMLElement>,
    render: () => null,
  };
}
