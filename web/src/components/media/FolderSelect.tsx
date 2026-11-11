"use client";

import { FolderAddOutlined, FolderOutlined } from "@ant-design/icons";
import { Select, type SelectProps } from "antd";
import { useState } from "react";
import { plain } from "@/components/FilterSelect";
import type { MediaFolder } from "@/lib/api";

/** "Không thư mục" as a choice: the library's root. */
const NONE = "\u0000none";

/** A folder as typed, the way the api keeps it: no empty parts, single spaces, forward slashes. */
export function cleanFolder(raw: string): string {
  return raw
    .normalize("NFC")
    .replaceAll("\\", "/")
    .split("/")
    .map((part) => part.split(/\s+/).filter(Boolean).join(" "))
    .filter((part) => part && part !== "." && part !== "..")
    .join("/");
}

/** A folder's line in a dropdown: its name, its count and the group whose "Tư liệu" it is. */
export function folderLabel({ folder, count, topic }: MediaFolder): string {
  return `${folder} (${count})${topic ? `, nhóm ${topic}` : ""}`;
}

/**
 * Every place a folder of the "Kho tư liệu" is chosen (adding items, "Chuyển thư mục", a group's "Tư liệu"): the
 * folders there are with their counts, and typing a new name offers "Tạo thư mục “…”", so a folder is picked rather
 * than typed again slightly differently. `value` "" is "Không thư mục" when `allowNone`; null is nothing chosen.
 * `forTopic`: a folder another group links is shown but cannot be picked.
 */
export default function FolderSelect({
  folders,
  value,
  onChange,
  allowNone = false,
  forTopic,
  ...props
}: Omit<SelectProps<string>, "value" | "onChange" | "options" | "showSearch" | "filterOption" | "onSearch"> & {
  folders: MediaFolder[];
  value: string | null;
  onChange: (folder: string | null) => void;
  allowNone?: boolean;
  forTopic?: number;
}) {
  const [typed, setTyped] = useState("");
  const name = cleanFolder(typed);
  const isNew = Boolean(name) && !folders.some((row) => row.folder === name);
  const options = [
    ...(isNew ? [{ value: name, label: `Tạo thư mục “${name}”`, icon: <FolderAddOutlined /> }] : []),
    ...(allowNone ? [{ value: NONE, label: "Không thư mục" }] : []),
    ...folders.map((row) => ({
      value: row.folder,
      label: folderLabel(row),
      disabled: forTopic !== undefined && row.topic_id !== null && row.topic_id !== forTopic,
    })),
  ];
  return (
    <Select<string>
      showSearch
      allowClear
      suffixIcon={<FolderOutlined />}
      placeholder="Chọn hoặc gõ tên thư mục mới…"
      notFoundContent="Gõ tên để tạo thư mục mới"
      {...props}
      value={value === null ? undefined : value === "" && allowNone ? NONE : value}
      searchValue={typed}
      onSearch={setTyped}
      // The "Tạo thư mục" line always shows while typing; the others match without accents or case.
      filterOption={(input, option) =>
        option?.value === name || plain(String(option?.label ?? "")).includes(plain(input))
      }
      onChange={(next) => {
        setTyped("");
        onChange(next === undefined ? null : next === NONE ? "" : next);
      }}
      options={options}
      optionRender={(option) => (
        <span>
          {option.data.icon} {option.data.label}
        </span>
      )}
    />
  );
}
