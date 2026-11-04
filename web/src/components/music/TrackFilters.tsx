"use client";

import { SearchOutlined } from "@ant-design/icons";
import { Flex, Input } from "antd";
import type { TrackFilters as Filters } from "./useTracks";
import { useMusicOptions } from "./useTracks";
import FilterSelect from "@/components/FilterSelect";

/** Topic, mood and name filters shared by the library page and the picker. */
export default function TrackFilters({ value, onChange }: { value: Filters; onChange: (value: Filters) => void }) {
  const { topics, moods } = useMusicOptions();
  return (
    <Flex wrap gap={12}>
      <Input
        aria-label="Tìm theo tên bài"
        prefix={<SearchOutlined />}
        placeholder="Tìm theo tên bài"
        allowClear
        value={value.q}
        onChange={(event) => onChange({ ...value, q: event.target.value })}
        // A set width: at 100% the box takes the whole row and pushes the two selects onto lines of their own.
        style={{ width: 260, maxWidth: "100%" }}
      />
      <FilterSelect
        aria-label="Lọc theo chủ đề"
        placeholder="Mọi chủ đề"
        value={value.topic}
        onChange={(topic) => onChange({ ...value, topic })}
        options={topics.map((item) => ({ value: item, label: item }))}
        style={{ width: 180 }}
      />
      <FilterSelect
        aria-label="Lọc theo mood"
        placeholder="Mọi mood"
        value={value.mood}
        onChange={(mood) => onChange({ ...value, mood })}
        options={moods.map((item) => ({ value: item, label: item }))}
        style={{ width: 180 }}
      />
    </Flex>
  );
}
