"use client";

import { TagsOutlined } from "@ant-design/icons";
import { Select, type SelectProps } from "antd";
import { plain } from "@/components/FilterSelect";
import type { MediaTag } from "@/lib/api";

/** A tag the way the api keeps it (media_tags.clean_tag): lowercase, no accents, words joined with "-"; "" if empty. */
export function cleanTag(raw: string): string {
  return plain(raw)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Every place tags are chosen ("Sửa thẻ", "Thêm thẻ", "Gỡ thẻ", adding items, the filter): the library's tags with
 * their counts come first, matched without accents, so a tag that is there is picked over a new one; Enter on what
 * was typed makes a new one, cleaned as the api will keep it ("Xoay Cổ" is `xoay-co`).
 */
export default function TagSelect({
  tags,
  value,
  onChange,
  allowNew = true,
  ...props
}: Omit<SelectProps<string[]>, "value" | "onChange" | "options" | "mode" | "filterOption"> & {
  tags: MediaTag[];
  value: string[];
  onChange: (tags: string[]) => void;
  /** False for a filter or "Gỡ thẻ": only the tags there are. */
  allowNew?: boolean;
}) {
  return (
    <Select<string[]>
      mode={allowNew ? "tags" : "multiple"}
      allowClear
      suffixIcon={<TagsOutlined />}
      tokenSeparators={[","]}
      {...props}
      value={value}
      // A chosen tag shows as itself, without the count its option has.
      labelRender={({ value: tag }) => String(tag)}
      onChange={(next) => onChange([...new Set(next.map(cleanTag).filter(Boolean))])}
      filterOption={(input, option) => plain(String(option?.value ?? "")).includes(cleanTag(input))}
      options={tags.map(({ tag, count }) => ({ value: tag, label: `${tag} (${count})` }))}
    />
  );
}
