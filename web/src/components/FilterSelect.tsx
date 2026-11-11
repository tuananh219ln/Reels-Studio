"use client";

import { Select, type SelectProps } from "antd";

/** Text compared without accents or case, so "vuon nha" finds "Vườn nhà". */
export function plain(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
}

/**
 * Every filter on a page's toolbar: typing searches its options (accents do not matter), × clears it, and with
 * nothing chosen it shows its placeholder ("Mọi trạng thái", "Mọi Fanpage"…), which is also what "all" means.
 */
export default function FilterSelect<T extends string | number>({
  value,
  ...props
}: Omit<SelectProps<T>, "value" | "showSearch" | "allowClear" | "filterOption"> & { value: T | null | undefined }) {
  return (
    <Select<T>
      showSearch
      allowClear
      value={value ?? undefined}
      filterOption={(input, option) => plain(String(option?.label ?? "")).includes(plain(input))}
      style={{ width: 180, ...props.style }}
      {...props}
    />
  );
}
